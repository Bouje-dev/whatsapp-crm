import json
import re
import os
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, HttpResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from discount.models import AutoReply, Flow
from django.db import transaction
from discount.activites import log_activity

# ---------------------
# Serialization Helpers
# ---------------------
def serialize_autoreply(obj, request=None):
    """Serialize AutoReply object to JSON-serializable dict"""
    media_url = None
    try:
        if getattr(obj, 'media_file', None) and obj.media_file:
            if request is not None:
                media_url = request.build_absolute_uri(obj.media_file.url)
            else:
                media_url = obj.media_file.url
    except Exception:
        media_url = None

    return {
        "id": obj.id,
        "trigger": obj.trigger,
        "match_type": obj.match_type,
        "response_type": obj.response_type,
        "response_text": obj.response_text,
        "media_url": media_url,
        "delay": getattr(obj, 'delay', 0),
        "active": obj.active,
        "created_at": obj.created_at.isoformat() if getattr(obj, "created_at", None) else None,
        "updated_at": obj.updated_at.isoformat() if getattr(obj, "updated_at", None) else None,
    }

 
def serialize_flow(obj):
    # جلب العقد
    nodes = []
    for n in obj.nodes.all():
        content_data = {}

        # --- 1. منطق خاص لعقدة Trigger ---
        if n.node_type == 'trigger':
            # نعتمد على إعدادات الـ Flow نفسه كمصدر للحقيقة
            if getattr(obj, 'trigger_on_start', False):
                content_data['match_type'] = 'conversation_start'
                content_data['keywords'] = ''
            else:
                content_data['match_type'] = 'contains' # القيمة الافتراضية
                content_data['keywords'] = getattr(obj, 'trigger_keywords', "")

        # --- 2. منطق خاص لعقدة النصوص ---
        elif n.node_type == 'text-message':
            content_data['text'] = n.content_text
            content_data['delay'] = getattr(n, 'delay', 0)

        # --- 3. منطق خاص لعقدة الميديا ---
        elif n.node_type == 'media-message':
            content_data['url'] = n.content_media_url  # رابط الصورة
            content_data['caption'] = n.content_text     # النص هو الكابشن
            content_data['mediaType'] = getattr(n, 'media_type', 'image')
            content_data['delay'] = getattr(n, 'delay', 0)

        # --- 4. AI Agent ---
        elif n.node_type == 'ai-agent':
            content_data['product_context'] = getattr(n, 'product_context', '') or ''
            content_data['context_source'] = getattr(n, 'context_source', 'MANUAL') or 'MANUAL'
            content_data['voice_enabled'] = getattr(n, 'voice_enabled', False)
            ac = getattr(n, 'ai_model_config', None) or {}
            content_data['ai_model_config'] = ac
            content_data['product_id'] = ac.get('product_id')
            content_data['delay'] = getattr(n, 'delay', 0)
            content_data['response_mode'] = getattr(n, 'response_mode', None) or 'TEXT_ONLY'
            content_data['node_voice_id'] = getattr(n, 'node_voice_id', None) or ''
            content_data['node_language'] = getattr(n, 'node_language', None) or ''
            content_data['node_gender'] = getattr(n, 'node_gender', None) or ''
            content_data['persona_id'] = getattr(n, 'persona_id', None)
            content_data['voice_stability'] = getattr(n, 'voice_stability', None)
            content_data['voice_similarity'] = getattr(n, 'voice_similarity', None)
            content_data['voice_speed'] = getattr(n, 'voice_speed', None)
            media_list = []
            try:
                for m in getattr(n, 'media_assets', []).all():
                    media_list.append({
                        'id': m.id,
                        'file_path': m.file.name if m.file else None,
                        'file_url': m.file.url if m.file else None,
                        'file_type': m.file_type or 'Image',
                        'description': m.description or '',
                    })
            except Exception:
                pass
            content_data['media'] = media_list

        # --- 5. Follow-up node ---
        elif n.node_type == 'follow-up':
            try:
                fu = getattr(n, 'follow_up_config', None)
                if fu:
                    content_data['delay_hours'] = getattr(fu, 'delay_hours', 6)
                    content_data['response_type'] = getattr(fu, 'response_type', 'TEXT') or 'TEXT'
                    content_data['ai_personalized'] = getattr(fu, 'ai_personalized', False)
                    content_data['caption'] = (getattr(fu, 'caption', None) or '') or ''
                    content_data['file_url'] = fu.file_attachment.url if fu.file_attachment else ''
                    content_data['file_path'] = fu.file_attachment.name if fu.file_attachment else ''
                else:
                    content_data['delay_hours'] = 6
                    content_data['response_type'] = 'TEXT'
                    content_data['ai_personalized'] = False
                    content_data['caption'] = ''
                    content_data['file_url'] = ''
                    content_data['file_path'] = ''
            except Exception:
                content_data['delay_hours'] = 6
                content_data['response_type'] = 'TEXT'
                content_data['ai_personalized'] = False
                content_data['caption'] = ''

        # --- 5b. Google Sheets node ---
        elif n.node_type == 'google-sheets':
            content_data['label'] = (n.content_text or '').strip() or 'Export to Google Sheets'

        # --- 6. أي عقد أخرى (أزرار، تأخير، إلخ) ---
        else:
            content_data['text'] = n.content_text
            content_data['delay'] = getattr(n, 'delay', 0)

        # تجميع العقدة
        nodes.append({
            "id": n.node_id,
            "type": n.node_type,
            "position": {"x": n.position_x, "y": n.position_y},
            "content": content_data,  # <-- هنا التغيير الجوهري: نرسل قاموساً وليس نصاً
        })

    # جلب الاتصالات
    connections = []
    for c in obj.connections.all():
        connections.append({
            "source": c.from_node.node_id,
            "target": c.to_node.node_id,
            "data": c.data if c.data else {},
        })

    return {
        "id": obj.id,
        "name": obj.name,
        "description": getattr(obj, "description", ""),
        "config": {
            "nodes": nodes,
            "connections": connections,
        },
        # إرسال الكلمات المفتاحية كحقل خارجي أيضاً (للاستخدام العام)
        "trigger_keywords": getattr(obj, "trigger_keywords", ""),
        "trigger_on_start": getattr(obj, "trigger_on_start", False), # مفيد للدييباغ
        "active": getattr(obj, "active", False),
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "updated_at": obj.updated_at.isoformat() if obj.updated_at else None,
    }

def match_autoreply_for_text(text, phone=None):
    """
    Find matching auto-reply for given text
    Returns the best matching AutoReply object or None
    """
    if not text:
        return None

    rules = AutoReply.objects.filter(active=True).order_by("-created_at")
    for rule in rules:
        try:
            if rule.match_type == "exact":
                if text.strip() == (rule.trigger or "").strip():
                    return rule
            elif rule.match_type == "starts_with":
                if text.strip().startswith((rule.trigger or "").strip()):
                    return rule
            elif rule.match_type == "regex":
                try:
                    if re.search(rule.trigger or "", text, re.IGNORECASE):
                        return rule
                except re.error:
                    continue
            else:  # contains (default)
                if (rule.trigger or "").strip() and (rule.trigger or "").strip().lower() in text.lower():
                    return rule
        except Exception:
            continue
    return None

# ---------------------
# Flow Processing Functions
# ---------------------
def find_automated_response(phone, message_text, media_type=None):
    """
    البحث عن رد تلقائي مناسب للرسالة الواردة - معدل بشكل كامل
    """
    try:
        print(f"🎯 START Automated response search for: '{message_text}' from {phone}")
        
        # البحث أولاً في الـ Flows النشطة
        active_flows = Flow.objects.filter(active=True)
        print(f"📁 Found {active_flows.count()} active flows")
        
        for flow in active_flows:
            print(f"🔍 Processing flow: {flow.name} (ID: {flow.id})")
            responses = process_flow_for_message(flow, message_text, phone, media_type)
            if responses:
                print(f"🎉 Found {len(responses)} responses in flow: {flow.name}")
                # زيادة عداد التشغيل
                if hasattr(flow, 'count'):
                    flow.count += 1
                    flow.save()
                return responses
            else:
                print(f"❌ No responses found in flow: {flow.name}")
        
        # إذا لم يوجد تطابق في الـ Flows، نبحث في الـ AutoReply
        print("🔍 Searching in AutoReply rules...")
        auto_reply = match_autoreply_for_text(message_text)
        if auto_reply:
            response = serialize_autoreply_response(auto_reply)
            if is_valid_response(response):
                print(f"✅ Found valid response in AutoReply: {auto_reply.trigger}")
                auto_reply.increment_usage()
                return [response]
            else:
                print(f"⚠️ AutoReply response is invalid: {response}")
        
        print("❌ No valid automated response found in any flow or autoreply")
        return None
        
    except Exception as e:
        print(f"💥 Error finding automated response: {e}")
        import traceback
        traceback.print_exc()
        return None

def is_valid_response(response_data):
    """
    التحقق من أن بيانات الرد صالحة للإرسال
    """
    if not response_data:
        return False
        
    response_type = response_data.get('type', 'text')
    
    if response_type == 'text':
        content = response_data.get('content', '').strip()
        return bool(content)  # يجب أن يكون هناك محتوى نصي
        
    elif response_type in ['image', 'audio', 'video', 'document']:
        media_url = response_data.get('media_url')
        return bool(media_url)  # يجب أن يكون هناك رابط وسائط
        
    return False



def process_flow_for_message(flow, message_text, phone, media_type=None):
    """
    معالجة تدفق معين للعثور على رد للرسالة - معدل بشكل كامل
    """
    try:
        print(f"🔍 START Processing flow: {flow.name} for message: '{message_text}'")
        
        flow_data = flow.flow_data
        if isinstance(flow_data, str):
            try:
                flow_data = json.loads(flow_data)
                print("✅ Flow data parsed from JSON")
            except json.JSONDecodeError as e:
                print(f"❌ Invalid JSON in flow data: {e}")
                flow_data = {}
        
        nodes = flow_data.get('nodes', [])
        connections = flow_data.get('connections', [])
        
        print(f"📊 Flow has {len(nodes)} nodes and {len(connections)} connections")
        
        # البحث عن عقدة trigger أولاً
        trigger_nodes = [node for node in nodes if node.get('type') == 'trigger']
        
        if not trigger_nodes:
            print("❌ No trigger node found in flow - cannot process")
            return None
            
        trigger_node = trigger_nodes[0]
        print(f"🎯 Found trigger node: {trigger_node.get('id')}")
        
        # التحقق من شروط المحفز أولاً - هذه هي النقطة الحاسمة
        if not check_trigger_conditions(trigger_node, message_text, phone, media_type):
            print("🚫 Trigger conditions NOT matched - stopping flow execution")
            return None
            
        print("🎉 Trigger conditions MATCHED - continuing flow execution")
        
        # الآن نبدأ التنفيذ من العقدة التالية لل trigger
        current_node = get_next_node(trigger_node['id'], connections, nodes)
        if not current_node:
            print("❌ No node after trigger - flow ends here")
            return None
            
        print(f"➡️ Moving to next node: {current_node.get('id')} ({current_node.get('type')})")
        
        visited_nodes = set()
        responses = []  # لتجميع جميع الردود
        
        # نبدأ معالجة العقد من العقدة التالية لل trigger
        while current_node and current_node['id'] not in visited_nodes:
            visited_nodes.add(current_node['id'])
            node_type = current_node.get('type')
            
            print(f"🔄 Processing node: {node_type} (ID: {current_node.get('id')})")
            
            if node_type == 'text-message':
                response = create_text_response(current_node)
                print(f"📝 Text node response: {response}")
                if response and is_valid_response(response):
                    print(f"✅ Adding text response: '{response.get('content')}'")
                    responses.append(response)
                else:
                    print("⚠️ Text node has empty or invalid content")
                    
            elif node_type == 'media-message':
                response = create_media_response(current_node)
                print(f"🖼️ Media node response: {response}")
                if response and is_valid_response(response):
                    print(f"✅ Adding media response")
                    responses.append(response)
                else:
                    print("⚠️ Media node has invalid data")
                    
            elif node_type == 'condition':
                condition_result = evaluate_condition(current_node, message_text, phone)
                print(f"🔀 Condition result: {condition_result}")
                next_node_id = get_condition_branch(current_node['id'], connections, condition_result)
                if next_node_id:
                    current_node = find_node_by_id(next_node_id, nodes)
                    print(f"↪️ Condition branch taken to: {current_node.get('id') if current_node else 'None'}")
                    continue
                else:
                    print("❌ No branch found for condition - stopping")
                    break
                    
            elif node_type == 'delay':
                delay = current_node.get('content', {}).get('duration', 0) if isinstance(current_node.get('content'), dict) else 0
                print(f"⏱️ Delay node: {delay} seconds")
                # نضيف تأخير كرد خاص
                if delay > 0:
                    responses.append({
                        'type': 'delay',
                        'duration': delay
                    })

            elif node_type == 'ai-agent':
                # AI Agent: Elite Sales Consultant prompt + product context + trust_score (JSON flow path)
                content = current_node.get('content', {}) or {}
                product_context = content.get('product_context', '').strip() or None
                try:
                    from ai_assistant.services import generate_reply_with_tools
                    from discount.orders_ai import (
                        extract_order_data_from_reply,
                        save_order_from_ai,
                        should_accept_order_data,
                        get_trust_score,
                        increment_trust_score,
                        reset_trust_score,
                    )
                    from discount.whatssapAPI.process_messages import format_order_confirmation
                    from django.db import transaction as db_transaction
                    conversation = [{"role": "customer", "body": message_text or ""}]
                    trust_score = get_trust_score(flow.channel_id, phone) if flow.channel_id else 0
                    result = generate_reply_with_tools(
                        conversation,
                        custom_instruction=None,
                        product_context=product_context,
                        trust_score=trust_score,
                    )
                    reply_text = (result.get("reply") or "").strip()
                    current_stage = result.get("stage")
                    order_was_saved = False
                    saved_order = None
                    if reply_text:
                        reply_text, order_data = extract_order_data_from_reply(reply_text)
                        if order_data and flow.channel_id and should_accept_order_data(conversation, order_data, current_stage=current_stage, trust_score=trust_score):
                            with db_transaction.atomic():
                                saved_order = save_order_from_ai(
                                    flow.channel,
                                    customer_phone=phone,
                                    customer_name=order_data.get("name"),
                                    customer_city=order_data.get("city") or order_data.get("address"),
                                    sku=order_data.get("sku") or None,
                                    product_name=order_data.get("product_name") or None,
                                    agent_name="AI Agent",
                                    bot_session_id=f"{getattr(flow.channel, 'id', '')}:{phone}"[:100] if flow.channel else None,
                                )
                            if saved_order:
                                order_was_saved = True
                    if order_was_saved and saved_order:
                        reply_text = format_order_confirmation(saved_order)
                    if flow.channel_id:
                        if order_was_saved:
                            reset_trust_score(flow.channel_id, phone)
                        else:
                            increment_trust_score(flow.channel_id, phone)
                except Exception as e:
                    print(f"❌ AI_AGENT node failed: {e}")
                    reply_text = None
                if reply_text:
                    responses.append({'type': 'text', 'content': reply_text, 'delay': content.get('delay', 0)})
                
            else:
                print(f"ℹ️ Unknown node type: {node_type}")
                
            # الانتقال للعقدة التالية
            next_node = get_next_node(current_node['id'], connections, nodes)
            if next_node:
                current_node = next_node
                print(f"➡️ Moving to next node: {current_node.get('id')} ({current_node.get('type')})")
            else:
                print("🏁 No more nodes - end of flow")
                break
                
        print(f"📬 Finished processing flow. Collected {len(responses)} responses")
        return responses if responses else None
        
    except Exception as e:
        print(f"💥 Error processing flow: {e}")
        import traceback
        traceback.print_exc()
        return None

def check_trigger_conditions(trigger_node, message_text, phone, media_type):
    """
    التحقق من شروط المحفز - معدل بشكل نهائي
    """
    try:
        print(f"🔍 فحص محفز للرسالة: '{message_text}'")
        
        # الحصول على محتوى المحفز
        content_data = trigger_node.get('content', {})
        
        # في الهيكل الجديد، content هو dictionary
        if isinstance(content_data, dict):
            keywords_str = content_data.get('keywords', '')
        else:
            # للتوافق مع الإصدارات القديمة
            keywords_str = str(content_data)
        
        print(f"🔍 كلمات المحفز: '{keywords_str}'")
        
        if not keywords_str or not keywords_str.strip():
            print("❌ المحفز لا يحتوي على كلمات مفتاحية - لا يتطابق")
            return False
            
        # تنظيف وتقسيم الكلمات المفتاحية
        keywords = [k.strip().lower() for k in keywords_str.split(',') if k.strip()]
        message_lower = message_text.lower().strip()
        
        print(f"🔍 الكلمات المفتاحية: {keywords}")
        print(f"🔍 الرسالة: '{message_lower}'")
        
        for keyword in keywords:
            if keyword and keyword in message_lower:
                print(f"✅ تطابق مع الكلمة المفتاحية: '{keyword}'")
                return True
        
        print(f"❌ لا يوجد تطابق مع أي كلمة مفتاحية")
        return False
        
    except Exception as e:
        print(f"❌ خطأ في فحص شروط المحفز: {e}")
        import traceback
        traceback.print_exc()
        return False



def evaluate_condition(condition_node, message_text, phone):
    """
    تقييم العقدة الشرطية - معدل للتعامل مع هيكل البيانات الجديد
    """
    try:
        content_data = condition_node.get('content', {})
        
        if isinstance(content_data, dict):
            condition_type = content_data.get('operator', 'text_contains')
            condition_value = content_data.get('value', '').lower()
            variable = content_data.get('variable', '')
        else:
            condition_type = 'text_contains'
            condition_value = str(content_data).lower()
            variable = ''
        
        message_lower = message_text.lower()
        
        print(f"🔍 Evaluating condition: {condition_type}, value: {condition_value}, variable: {variable}")
        
        if condition_type == 'text_contains':
            return condition_value in message_lower
        elif condition_type == 'text_exact':
            return message_text.strip() == condition_value.strip()
        elif condition_type == 'text_starts_with':
            return message_lower.startswith(condition_value)
        elif condition_type == 'text_ends_with':
            return message_lower.endswith(condition_value)
        elif condition_type == 'text_regex':
            try:
                return bool(re.search(condition_value, message_text, re.IGNORECASE))
            except re.error:
                return False
        else:
            return False
            
    except Exception as e:
        print(f"❌ Error evaluating condition: {e}")
        return False
    




def get_next_node(node_id, connections, nodes):
    """
    الحصول على العقدة التالية في التدفق
    """
    try:
        for connection in connections:
            if connection['source'] == node_id:
                return find_node_by_id(connection['target'], nodes)
        return None
    except Exception as e:
        print(f"❌ Error getting next node: {e}")
        return None

def get_condition_branch(condition_node_id, connections, condition_result):
    """
    الحصول على الفرع المناسب بناءً على نتيجة الشرط
    """
    try:
        true_branch = None
        false_branch = None
        
        for connection in connections:
            if connection['source'] == condition_node_id:
                if connection.get('label') == 'true' or true_branch is None:
                    true_branch = connection['target']
                else:
                    false_branch = connection['target']
        
        return true_branch if condition_result else false_branch
            
    except Exception as e:
        print(f"❌ Error getting condition branch: {e}")
        return None

def find_node_by_id(node_id, nodes):
    """
    البحث عن عقدة بواسطة ID - معدل
    """
    for node in nodes:
        if node['id'] == node_id:
            return node
    
    print(f"❌ Node not found with ID: {node_id}")
    return None


def create_text_response(text_node):
    """
    إنشاء رد نصي من عقدة نصية - معدل للتعامل مع هيكل البيانات الجديد
    """
    try:
        # في الهيكل الجديد، content هو dictionary وليس نصاً مباشراً
        content_data = text_node.get('content', {})
        
        # استخراج النص من dictionary
        if isinstance(content_data, dict):
            content = content_data.get('text', '')
            delay = content_data.get('delay', 0)
        else:
            # إذا كان content نصاً مباشراً (للتوافق مع الإصدارات القديمة)
            content = str(content_data)
            delay = 0
        
        return {
            'type': 'text',
            'content': content,
            'delay': delay,
            'node_type': 'text-message'
        }
    except Exception as e:
        print(f"❌ Error creating text response: {e}")
        return None


def create_media_response(media_node):
    """
    إنشاء رد وسائط من عقدة وسائط - معدل للتعامل مع الوسائط
    """
    try:
        content_data = media_node.get('content', {})
        
        if isinstance(content_data, dict):
            content = content_data.get('caption', '')
            media_type = content_data.get('mediaType', 'image')  # لاحظ الحرف الكبير
            delay = content_data.get('delay', 0)
            
            # محاولة الحصول على media_url من مصادر مختلفة
            media_url = content_data.get('media_url') or content_data.get('mediaUrl') or content_data.get('url')
            
        else:
            content = str(content_data)
            media_url = None
            media_type = 'image'
            delay = 0
        
        # إذا لم يكن هناك media_url، لا نرجع رد وسائط
        if not media_url:
            print("❌ No media URL found for media message")
            return None
            
        return {
            'type': 'media',
            'media_type': media_type,
            'media_url': media_url,
            'content': content,
            'delay': delay,
            'node_type': 'media-message'
        }
    except Exception as e:
        print(f"❌ Error creating media response: {e}")
        return None

def serialize_autoreply_response(auto_reply):
    """
    تحويل كائن AutoReply إلى تنسيق رد
    """
    try:
        media_url = None
        if auto_reply.media_file:
            try:
                media_url = auto_reply.media_file.url
            except Exception:
                media_url = None

        return {
            'type': auto_reply.response_type,
            'content': auto_reply.response_text,
            'media_url': media_url,
            'delay': getattr(auto_reply, 'delay', 0),
            'node_type': 'autoreply'
        }
    except Exception as e:
        print(f"❌ Error serializing autoreply: {e}")
        return None

# ---------------------
# Page Views
# ---------------------
def flow_builder_page(request):
    """Flow Builder Page"""
    return render(request, "autobot/flow_builder.html")

# ---------------------
# AutoReply APIs (autobot_* endpoints)
# ---------------------
@csrf_exempt
def autobot_rules_list(request):
    """
    GET: قائمة القواعد (rules) المستخدمة في الواجهة.
    يرد بـ { rules: [...] }
    """
    if request.method != 'GET':
        return HttpResponseBadRequest('GET required')
    qs = AutoReply.objects.order_by('-created_at')
    data = [serialize_autoreply(a, request=request) for a in qs]
    return JsonResponse({'rules': data})

@csrf_exempt
def autobot_rule_get(request):
    """
    GET ?id=<id> => إرجاع قاعدة واحدة
    """
    if request.method != 'GET':
        return HttpResponseBadRequest('GET required')
    rule_id = request.GET.get('id')
    if not rule_id:
        return JsonResponse({'error': 'id required'}, status=400)
    ar = get_object_or_404(AutoReply, pk=rule_id)
    return JsonResponse({'rule': serialize_autoreply(ar, request=request)})

@csrf_exempt
def autobot_add_rule(request):
    """
    POST: إنشاء أو تعديل قاعدة.
    يقبل multipart/form-data أو JSON.
    حقل id في JSON يعني تحديث.
    """
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required')

    # تنسيق payload (multipart أو json)
    if request.content_type and request.content_type.startswith('multipart'):
        trigger = request.POST.get('trigger', '').strip()
        match_type = request.POST.get('match_type', 'contains')
        response_type = request.POST.get('response_type', 'text')
        response_text = request.POST.get('response_text', '')
        media = request.FILES.get('media')
        edit_id = request.POST.get('id') or None
    else:
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            return JsonResponse({'error': 'invalid json'}, status=400)
        trigger = payload.get('trigger', '').strip()
        match_type = payload.get('match_type', 'contains')
        response_type = payload.get('response_type', 'text')
        response_text = payload.get('response_text', '')
        media = None
        edit_id = payload.get('id') or None

    if not trigger:
        return JsonResponse({'error': 'trigger required'}, status=400)

    if edit_id:
        ar = get_object_or_404(AutoReply, pk=edit_id)
        ar.trigger = trigger
        ar.match_type = match_type
        ar.response_type = response_type
        ar.response_text = response_text
        if media:
            ar.media_file = media
        ar.active = True
        ar.updated_at = timezone.now()
        ar.save()
    else:
        ar = AutoReply.objects.create(
            trigger=trigger,
            match_type=match_type,
            response_type=response_type,
            response_text=response_text,
            active=True
        )
        if media:
            ar.media_file = media
            ar.save()

    return JsonResponse({'item': serialize_autoreply(ar, request=request)})

@csrf_exempt
def autobot_delete_rule(request):
    """
    POST: حذف القاعدة. body: { id: <id> } أو form id=<id>
    """
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required')

    if request.content_type and request.content_type.startswith('multipart'):
        rid = request.POST.get('id')
    else:
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
            rid = payload.get('id')
        except Exception:
            rid = None

    if not rid:
        return JsonResponse({'error': 'id required'}, status=400)

    try:
        ar = AutoReply.objects.get(pk=rid)
        ar.delete()
        return JsonResponse({'ok': True})
    except AutoReply.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)

@csrf_exempt
def autobot_match_message(request):
    """
    مساعد لاختبار المطابقة: POST { text: "..." } => يُرجع القاعدة المطابقة (إن وُجدت)
    """
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required')
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'error': 'invalid json'}, status=400)
    text = payload.get('text', '')
    ar = match_autoreply_for_text(text)
    if not ar:
        return JsonResponse({'matched': False})
    return JsonResponse({'matched': True, 'rule': serialize_autoreply(ar, request=request)})

# ---------------------
# AutoReply APIs (api_* endpoints)
# ---------------------
@require_http_methods(["GET"])
def api_list_autoreplies(request):
    """Get all auto-reply rules"""
    qs = AutoReply.objects.order_by("-created_at")
    data = [serialize_autoreply(a, request=request) for a in qs]
    return JsonResponse({"items": data})

@require_http_methods(["GET"])
def api_get_autoreply(request, pk):
    """Get specific auto-reply rule"""
    ar = get_object_or_404(AutoReply, pk=pk)
    return JsonResponse({"item": serialize_autoreply(ar, request=request)})

@csrf_exempt
@require_http_methods(["POST"])
def api_create_autoreply(request):
    """Create new auto-reply rule"""
    try:
        if request.content_type.startswith("multipart"):
            trigger = (request.POST.get("trigger") or "").strip()
            match_type = request.POST.get("match_type") or "contains"
            response_type = request.POST.get("response_type") or "text"
            response_text = request.POST.get("response_text") or ""
            delay = int(request.POST.get("delay") or 0)
            media = request.FILES.get("media")
        else:
            payload = json.loads(request.body.decode("utf-8") or "{}")
            trigger = (payload.get("trigger") or "").strip()
            match_type = payload.get("match_type") or "contains"
            response_type = payload.get("response_type") or "text"
            response_text = payload.get("response_text") or ""
            delay = int(payload.get("delay") or 0)
            media = None
    except Exception as e:
        return JsonResponse({"error": "invalid payload", "details": str(e)}, status=400)

    if not trigger:
        return JsonResponse({"error": "trigger required"}, status=400)

    ar = AutoReply(
        trigger=trigger,
        match_type=match_type,
        response_type=response_type,
        response_text=response_text,
        delay=delay,
        active=True,
    )
    ar.save()
    if media:
        ar.media_file = media
        ar.save()

    log_activity('autoreply_created', f"AutoReply created: trigger='{trigger}' ({match_type})", request=request, related_object=ar)
    return JsonResponse({"item": serialize_autoreply(ar, request=request)}, status=201)

@csrf_exempt
@require_http_methods(["POST", "PUT", "PATCH"])
def api_update_autoreply(request, pk):
    """Update auto-reply rule"""
    ar = get_object_or_404(AutoReply, pk=pk)
    try:
        if request.content_type.startswith("multipart"):
            trigger = request.POST.get("trigger")
            match_type = request.POST.get("match_type")
            response_type = request.POST.get("response_type")
            response_text = request.POST.get("response_text")
            delay = request.POST.get("delay")
            active = request.POST.get("active")
            media = request.FILES.get("media")
        else:
            payload = json.loads(request.body.decode("utf-8") or "{}")
            trigger = payload.get("trigger")
            match_type = payload.get("match_type")
            response_type = payload.get("response_type")
            response_text = payload.get("response_text")
            delay = payload.get("delay")
            active = payload.get("active")
            media = None
    except Exception as e:
        return JsonResponse({"error": "invalid payload", "details": str(e)}, status=400)

    if trigger is not None:
        ar.trigger = trigger
    if match_type is not None:
        ar.match_type = match_type
    if response_type is not None:
        ar.response_type = response_type
    if response_text is not None:
        ar.response_text = response_text
    if delay is not None:
        ar.delay = int(delay)
    if active is not None:
        ar.active = bool(active)

    ar.updated_at = timezone.now()
    ar.save()

    if media:
        ar.media_file = media
        ar.save()

    log_activity('autoreply_updated', f"AutoReply #{ar.pk} updated: trigger='{ar.trigger}'", request=request, related_object=ar)
    return JsonResponse({"item": serialize_autoreply(ar, request=request)})

@csrf_exempt
@require_http_methods(["POST", "DELETE"])
def api_delete_autoreply(request, pk):
    """Delete auto-reply rule"""
    ar = get_object_or_404(AutoReply, pk=pk)
    trigger_name = ar.trigger
    ar.delete()
    log_activity('autoreply_deleted', f"AutoReply deleted: trigger='{trigger_name}'", request=request)
    return JsonResponse({"ok": True})

@csrf_exempt
@require_http_methods(["POST"])
def api_upload_media_for_autoreply(request):
    """Upload media for auto-reply rules"""
    if not request.content_type.startswith("multipart"):
        return JsonResponse({"error": "multipart/form-data required"}, status=400)

    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        return JsonResponse({"error": "file required"}, status=400)

    ar_id = request.POST.get("autoreply_id")
    if ar_id:
        ar = get_object_or_404(AutoReply, pk=int(ar_id))
    else:
        trigger = request.POST.get("trigger", "").strip() or "__media__"
        match_type = request.POST.get("match_type", "contains")
        response_type = request.POST.get("response_type", "image")
        response_text = request.POST.get("response_text", "")
        delay = int(request.POST.get("delay") or 0)

        ar = AutoReply.objects.create(
            trigger=trigger,
            match_type=match_type,
            response_type=response_type,
            response_text=response_text,
            delay=delay,
            active=True,
        )

    ar.media_file = uploaded_file
    ar.save()

    return JsonResponse({"item": serialize_autoreply(ar, request=request)})

@csrf_exempt
@require_http_methods(["POST"])
def api_match_message(request):
    """API endpoint to match messages with auto-reply rules"""
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        text = (payload.get("text") or "").strip()
        phone = payload.get("phone")
    except Exception as e:
        return JsonResponse({"error": "invalid json", "details": str(e)}, status=400)

    if not text:
        return JsonResponse({"matched": False, "reason": "empty text"})

    matched_rule = match_autoreply_for_text(text, phone)

    if not matched_rule:
        return JsonResponse({"matched": False})

    reply_data = {
        "autoreply_id": matched_rule.id,
        "response_type": matched_rule.response_type,
        "response_text": matched_rule.response_text,
        "delay": getattr(matched_rule, "delay", 0),
        "media_url": request.build_absolute_uri(matched_rule.media_file.url) if getattr(matched_rule, "media_file", None) else None,
    }

    return JsonResponse({"matched": True, "reply": reply_data})

# ---------------------
# Flow APIs (autobot_* endpoints)
# ---------------------
@csrf_exempt
def autobot_flows_list(request):
    """
    GET: قائمة الـ Flows المتوفرة.
    يرد بـ { flows: [{id, name}, ...] }
    """
    if request.method != 'GET':
        return HttpResponseBadRequest('GET required')
    qs = Flow.objects.order_by('-created_at')
    items = []
    for f in qs:
        items.append({
            'id': f.id,
            'name': getattr(f, 'name', '') or f.id,
            'created_at': getattr(f, 'created_at', None).isoformat() if getattr(f, 'created_at', None) else None
        })
    return JsonResponse({'flows': items})

@csrf_exempt
def autobot_save_flow(request):
    """
    حفظ التدفق مع معالجة محسنة للبيانات
    """
    print("💾 محاولة حفظ التدفق...")
    
    try:
        # معالجة البيانات الواردة
        if request.content_type and 'application/json' in request.content_type:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        else:
            # دعم multipart/form-data أيضًا
            payload = json.loads(request.POST.get('data', '{}'))
        
        print("📦 البيانات المستلمة:", json.dumps(payload, ensure_ascii=False)[:500])
        
        flow_data = payload.get('flow')
        flow_id = payload.get('id')
        name = payload.get('name') or payload.get('flow_name') or f'Flow {timezone.now().strftime("%Y%m%d%H%M%S")}'
        description = payload.get('description', '')
        trigger_keywords = payload.get('trigger_keywords', '')

        if not flow_data:
            return JsonResponse({
                'error': 'missing_flow_data',
                'message': 'بيانات التدفق مطلوبة'
            }, status=400)

        # التحقق من هيكل البيانات
        if not isinstance(flow_data, dict):
            return JsonResponse({
                'error': 'invalid_flow_format', 
                'message': 'بيانات التدفق يجب أن تكون كائن JSON صالح'
            }, status=400)

        nodes = flow_data.get('nodes', [])
        connections = flow_data.get('connections', [])
        
        print(f"🔍 تم استلام {len(nodes)} عقدة و {len(connections)} اتصال")

        # التحقق من صحة البيانات
        if not nodes:
            return JsonResponse({
                'error': 'no_nodes',
                'message': 'التدفق يجب أن يحتوي على عقد على الأقل'
            }, status=400)

        try:
            if flow_id:
                # تحديث تدفق موجود
                flow_obj = get_object_or_404(Flow, pk=flow_id)
                flow_obj.name = name
                flow_obj.description = description
                flow_obj.trigger_keywords = trigger_keywords
                flow_obj.config = flow_data
                flow_obj.updated_at = timezone.now()
                flow_obj.save()
                
                print(f"✅ تم تحديث التدفق: {flow_obj.id}")
            else:
                # إنشاء تدفق جديد
                flow_obj = Flow.objects.create(
                    name=name,
                    description=description,
                    trigger_keywords=trigger_keywords,
                    config=flow_data
                )
                print(f"✅ تم إنشاء تدفق جديد: {flow_obj.id}")

            # التحقق من صحة التدفق
            is_valid, validation_message = flow_obj.validate_flow_data()
            
            return JsonResponse({
                'ok': True,
                'id': flow_obj.id,
                'name': flow_obj.name,
                'validation': {
                    'is_valid': is_valid,
                    'message': validation_message
                },
                'nodes_count': len(nodes),
                'connections_count': len(connections)
            })
            
        except Exception as e:
            print(f"❌ خطأ في حفظ التدفق: {str(e)}")
            return JsonResponse({
                'error': 'save_failed',
                'message': f'فشل في حفظ التدفق: {str(e)}'
            }, status=500)

    except json.JSONDecodeError as e:
        print(f"❌ خطأ في تحليل JSON: {str(e)}")
        return JsonResponse({
            'error': 'invalid_json',
            'message': 'بيانات JSON غير صالحة'
        }, status=400)
    except Exception as e:
        print(f"❌ خطأ غير متوقع: {str(e)}")
        return JsonResponse({
            'error': 'unexpected_error',
            'message': f'حدث خطأ غير متوقع: {str(e)}'
        }, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def autobot_load_flow(request):
    """
    تحميل التدفق مع معالجة محسنة للبيانات
    """
    fid = request.GET.get('id')
    if not fid:
        return JsonResponse({'error': 'id_required', 'message': 'معرف التدفق مطلوب'}, status=400)
        
    try:
        flow_obj = get_object_or_404(Flow, pk=fid)
        
        # استخدام البيانات مباشرة من JSONField
        flow_data = flow_obj.flow_data or {'nodes': [], 'connections': []}
        
        # التحقق من أن البيانات تحتوي على الهيكل الصحيح
        if not isinstance(flow_data, dict):
            flow_data = {'nodes': [], 'connections': []}
            
        # تأكد من وجود القيم الأساسية
        if 'nodes' not in flow_data:
            flow_data['nodes'] = []
        if 'connections' not in flow_data:
            flow_data['connections'] = []
            
        print(f"📥 تحميل التدفق {fid}: {len(flow_data.get('nodes', []))} عقدة")
        
        # تسجيل البيانات للتصحيح
        for i, node in enumerate(flow_data.get('nodes', [])[:3]):  # أول 3 عقد فقط للتصحيح
            print(f"  العقدة {i}: {node.get('type')} - {node.get('id')}")
            if 'content' in node:
                print(f"    المحتوى: {node['content'][:100]}...")

        response_data = {
            'flow': flow_data,
            'id': flow_obj.id,
            'name': flow_obj.name,
            'description': flow_obj.description,
            'trigger_keywords': flow_obj.trigger_keywords,
            'active': flow_obj.active,
            'nodes_count': len(flow_data.get('nodes', [])),
            'connections_count': len(flow_data.get('connections', []))
        }
        
        return JsonResponse(response_data)
        
    except Exception as e:
        print(f"❌ خطأ في تحميل التدفق: {str(e)}")
        return JsonResponse({
            'error': 'load_failed', 
            'message': f'فشل في تحميل التدفق: {str(e)}'
        }, status=500)


@csrf_exempt
def autobot_delete_flow(request):
    """
    POST { id } => حذف فلو
    """
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required')
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except Exception:
        return JsonResponse({'error': 'invalid json'}, status=400)
    fid = payload.get('id')
    if not fid:
        return JsonResponse({'error': 'id required'}, status=400)
    try:
        f = Flow.objects.get(pk=fid)
        f.delete()
        return JsonResponse({'ok': True})
    except Flow.DoesNotExist:
        return JsonResponse({'error': 'not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': 'failed', 'details': str(e)}, status=500)

# ---------------------
# Flow APIs (api_* endpoints)
# ---------------------
@require_http_methods(["GET"])
def api_list_flows(request):
    channel_id = request.GET.get("channel_id")
    if channel_id == 'null':
        return JsonResponse({"items": []})
    if channel_id:
        qs = Flow.objects.filter(channel_id=channel_id).order_by("-created_at")
    else:
        qs = Flow.objects.order_by("-created_at")

    # qs = Flow.objects.order_by("-created_at")
    data = [serialize_flow(f) for f in qs]
    return JsonResponse({"items": data})

@require_http_methods(["GET"])
def api_get_flow(request, pk):
    f = get_object_or_404(Flow, pk=pk)
    return JsonResponse({"item": serialize_flow(f)})




def debug_flow_data(flow_data, title="تصحيح بيانات التدفق"):
    """
    دالة مساعدة لتصحيح بيانات التدفق - معدلة
    """
    print(f"\n🔍 {title}")
    print("=" * 50)
    
    if not flow_data:
        print("❌ بيانات التدفق فارغة")
        return
    
    nodes = flow_data.get('nodes', [])
    connections = flow_data.get('connections', [])
    
    print(f"📊 العدد: {len(nodes)} عقدة, {len(connections)} اتصال")
    
    for i, node in enumerate(nodes):
        print(f"\n🟢 العقدة {i + 1}:")
        print(f"   ID: {node.get('id')}")
        print(f"   النوع: {node.get('type')}")
        
        # عرض المحتوى بشكل آمن
        content = node.get('content', {})
        if content:
            content_str = str(content)
            # التحقق من أن content_str نص قبل عمل slicing
            if isinstance(content_str, str) and len(content_str) > 100:
                print(f"   المحتوى: {content_str[:100]}...")
            else:
                print(f"   المحتوى: {content_str}")
        else:
            print(f"   المحتوى: لا يوجد")
        
        print(f"   البيانات: {list(node.keys())}")
        
    for i, connection in enumerate(connections):
        print(f"\n🔗 الاتصال {i + 1}:")
        print(f"   من: {connection.get('source')}")
        print(f"   إلى: {connection.get('target')}")
# استخدم هذه الدالة في دوال الحفظ والتحميل للتصحيح

@csrf_exempt
@require_http_methods(["POST"])
def api_create_flow(request):
    """إنشاء تدفق جديد مع تحقق محسن من العقد"""
    print("🚀 بدء إنشاء تدفق جديد...")
    
    try:
        # معالجة application/json
        if request.content_type and 'application/json' in request.content_type:
            print("📝 معالجة application/json")
            
            if not request.body:
                return JsonResponse({"error": "Empty request body"}, status=400)
                
            body_str = request.body.decode('utf-8')
            print(f"📦 data from Flow builder" , body_str)
            
            try:
                payload = json.loads(body_str)
                name = payload.get('name', 'Untitled Flow').strip()
                description = payload.get('description', '').strip()
                trigger_keywords = payload.get('trigger_keywords', '').strip()
                config = payload.get('config', {})
            except json.JSONDecodeError as e:
                return JsonResponse({
                    "error": "Invalid JSON", 
                    "details": str(e)
                }, status=400)
                
        else:
            return JsonResponse({
                "error": "Unsupported content type", 
                "content_type": request.content_type
            }, status=400)
        
        # التحقق من البيانات الأساسية
        if not name:
            return JsonResponse({
                "error": "Flow name is required"
            }, status=400)
        
        # التحقق من هيكل التهيئة
        if not isinstance(config, dict):
            config = {}
            
        # تأكد من وجود الهيكل الأساسي
        if 'nodes' not in config:
            config['nodes'] = []
        if 'connections' not in config:
            config['connections'] = []
        
        print(f"🎯 إنشاء التدفق: {name}")
        print(f"📊 العدد: {len(config.get('nodes', []))} عقدة, {len(config.get('connections', []))} اتصال")
        
        # 🔍 فحص شامل للعقد - هذا هو الجزء المهم
        debug_flow_nodes(config.get('nodes', []))
        
        # إنشاء التدفق
        flow_obj = Flow.objects.create(
            name=name,
            description=description,
            trigger_keywords=trigger_keywords,
            flow_data=config,
            active=True
        )
        
        print(f"✅ تم إنشاء التدفق بنجاح. ID: {flow_obj.id}")
        
        return JsonResponse({
            "success": True,
            "item": serialize_flow(flow_obj),
            "message": "تم إنشاء التدفق بنجاح"
        }, status=201)
        
    except Exception as e:
        print(f"❌ خطأ غير متوقع في إنشاء التدفق: {str(e)}")
        import traceback
        traceback.print_exc()
        return JsonResponse({
            "error": "Server error", 
            "details": str(e)
        }, status=500)

def debug_flow_nodes(nodes):
    """
    فحص تفصيلي للعقد للتأكد من وجود Trigger وصحة البيانات
    """
    print("\n🔍 فحص تفصيلي للعقد:")
    print("=" * 60)
    
    trigger_nodes = []
    text_nodes = []
    media_nodes = []
    other_nodes = []
    
    for i, node in enumerate(nodes):
        node_type = node.get('type', 'unknown')
        node_id = node.get('id', 'no-id')
        content = node.get('content', {})
        
        print(f"\n📋 العقدة {i+1}:")
        print(f"   🆔 ID: {node_id}")
        print(f"   📝 النوع: {node_type}")
        print(f"   📦 المحتوى: {content}")
        print(f"   🔑 المفاتيح: {list(content.keys()) if isinstance(content, dict) else 'N/A'}")
        
        if node_type == 'trigger':
            trigger_nodes.append(node)
            keywords = content.get('keywords', '') if isinstance(content, dict) else ''
            print(f"   🎯 كلمات المحفز: '{keywords}'")
            
        elif node_type == 'text-message':
            text_nodes.append(node)
            text_content = content.get('text', '') if isinstance(content, dict) else ''
            print(f"   💬 نص الرسالة: '{text_content}'")
            
        elif node_type == 'media-message':
            media_nodes.append(node)
            media_type = content.get('mediaType', '') if isinstance(content, dict) else ''
            print(f"   🖼️ نوع الوسائط: {media_type}")
            
        else:
            other_nodes.append(node)
    
    print(f"\n📊 الإحصائيات:")
    print(f"   🎯 عقد المحفز: {len(trigger_nodes)}")
    print(f"   💬 عقد النص: {len(text_nodes)}") 
    print(f"   🖼️ عقد الوسائط: {len(media_nodes)}")
    print(f"   ❓ عقد أخرى: {len(other_nodes)}")
    
    # تحذيرات مهمة
    if len(trigger_nodes) == 0:
        print("❌ ⚠️  تحذير: لا توجد عقدة محفز (Trigger) في التدفق!")
        print("   التدفق لن يعمل بدون عقدة محفز لتحديد متى يبدأ.")
    
    for trigger_node in trigger_nodes:
        content = trigger_node.get('content', {})
        if isinstance(content, dict):
            keywords = content.get('keywords', '')
            if not keywords.strip():
                print("❌ ⚠️  تحذير: عقدة المحفز لا تحتوي على كلمات مفتاحية!")
    
    for text_node in text_nodes:
        content = text_node.get('content', {})
        if isinstance(content, dict):
            text_content = content.get('text', '')
            if not text_content.strip():
                print("⚠️  تحذير: عقدة نصية تحتوي على نص فارغ!")







@csrf_exempt
@require_http_methods(["POST", "PUT", "PATCH"])
def api_update_flow(request, pk):
    f = get_object_or_404(Flow, pk=pk)
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return JsonResponse({"error": "invalid json"}, status=400)

    name = payload.get("name")
    config = payload.get("config")
    active = payload.get("active")

    if name is not None:
        f.name = name
    if config is not None:
        f.config = config if isinstance(config, dict) else {}
    if active is not None:
        f.active = bool(active)
    f.updated_at = timezone.now()
    f.save()
    return JsonResponse({"item": serialize_flow(f)})

@csrf_exempt
@require_http_methods(["POST", "DELETE"])
def api_delete_flow(request, pk):
    f = get_object_or_404(Flow, pk=pk)
    flow_name = f.name
    f.delete()
    log_activity('flow_deleted', f"Flow deleted: '{flow_name}'", request=request)
    return JsonResponse({"ok": True})

















# =====================
# FLOW APIs (autobot_* endpoints) - المحسنة
# =====================

 
@csrf_exempt
 
@csrf_exempt
@require_http_methods(["POST"])
def autobot_validate_flow(request):
    """
    التحقق من صحة التدفق قبل الحفظ
    """
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        flow_data = payload.get('flow', {})
        
        # محاكاة كائن Flow للتحقق
        class TempFlow:
            def __init__(self, flow_data):
                self.flow_data = flow_data
            
            def get_nodes(self):
                return self.flow_data.get('nodes', [])
            
            def get_connections(self):
                return self.flow_data.get('connections', [])
        
        temp_flow = TempFlow(flow_data)
        
        # التحقق من الصحة
        nodes = temp_flow.get_nodes()
        connections = temp_flow.get_connections()
        
        issues = []
        
        # التحقق من العقد
        if not nodes:
            issues.append("لا توجد عقد في التدفق")
        
        # التحقق من الاتصالات
        node_ids = {node.get('id') for node in nodes}
        for i, connection in enumerate(connections):
            if connection.get('source') not in node_ids:
                issues.append(f"الاتصال {i} يشير إلى عقدة مصدر غير موجودة: {connection.get('source')}")
            if connection.get('target') not in node_ids:
                issues.append(f"الاتصال {i} يشير إلى عقدة هدف غير موجودة: {connection.get('target')}")
        
        # التحقق من عقدة البداية
        start_nodes = [node for node in nodes if node.get('type') in ['trigger', 'start', 'text-message']]
        if not start_nodes:
            issues.append("لا توجد عقدة بداية مناسبة في التدفق")
        
        return JsonResponse({
            'valid': len(issues) == 0,
            'issues': issues,
            'summary': {
                'nodes_count': len(nodes),
                'connections_count': len(connections),
                'start_nodes_count': len(start_nodes)
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'valid': False,
            'issues': [f'خطأ في التحقق: {str(e)}']
        })


@csrf_exempt
@require_http_methods(["POST"])
def autobot_duplicate_flow(request):



    """
    نسخ تدفق موجود
    """
    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
        flow_id = payload.get('id')
        
        if not flow_id:
            return JsonResponse({'error': 'id_required'}, status=400)
            
        original_flow = get_object_or_404(Flow, pk=flow_id)
        
        # إنشاء نسخة جديدة
        new_flow = Flow.objects.create(
            name=f"{original_flow.name} (نسخة)",
            description=original_flow.description,
            flow_data=original_flow.flow_data,
            trigger_keywords=original_flow.trigger_keywords
        )
        
        return JsonResponse({
            'ok': True,
            'id': new_flow.id,
            'name': new_flow.name,
            'message': 'تم نسخ التدفق بنجاح'
        })
        
    except Exception as e:
        return JsonResponse({
            'error': 'duplication_failed',
            'message': f'فشل في نسخ التدفق: {str(e)}'
        }, status=500)
    












# new flow system of saving 
 

from django.db import transaction
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from discount.models import WhatsAppChannel  # تأكد من المسارات
from discount.models import Flow, Node, Connection # تأكد من المسارات

class SaveFlowView(APIView):

    def post(self, request):
        data = request.data

        # 1. استخراج البيانات الأساسية
        name = data.get("name")
        channel_id = data.get("channel_id")

        description = data.get("description", "")
        config = data.get("config", {})
        
        nodes_data = config.get("nodes", [])
        connections_data = config.get("connections", [])

        if not name:
            return Response({"error": "Missing flow name"}, status=status.HTTP_400_BAD_REQUEST)
        
        if not channel_id:
            return Response({"error": "Missing channel ID"}, status=status.HTTP_400_BAD_REQUEST)

        # ---------------------------------------------------------
        # 2. منطق التحقق من القناة (Admin vs Agent) - التعديل المطلوب
        # ---------------------------------------------------------
        user = request.user
        channel = None

        # التحقق مما إذا كان المستخدم أدمن أو سوبر يوزر (يبحث في المالك owner)
        if user.is_superuser or getattr(user, 'is_team_admin', False):
            channel = WhatsAppChannel.objects.filter(id=channel_id, owner=user).first()
        
        # التحقق مما إذا كان موظفاً عادياً (يبحث في الموكلين assigned_agents)
        else:
            channel = WhatsAppChannel.objects.filter(id=channel_id, assigned_agents=user).first()

        # إذا لم يتم العثور على القناة أو ليست لديه صلاحية
        if not channel:
            return Response({"error": "Invalid channel or permission denied"}, status=status.HTTP_403_FORBIDDEN)

        # ---------------------------------------------------------
        # 3. عملية الحفظ الآمنة (Transaction Atomic)
        # ---------------------------------------------------------
        try:
            with transaction.atomic():
                # أ) إنشاء الفلو
                flow = Flow.objects.create(
                    channel=channel,
                    name=name,
                    description=description  , 
                     user=request.user,
                )

                # خريطة لربط الـ ID القادم من الفرونت إند مع الـ ID الحقيقي في الداتابيز
                node_map = {}

                # ب) حفظ العقد (Nodes)
                for n in nodes_data:
                    # إصلاح خطأ استخراج النوع
                    node_type_str = n.get("type") 
                    
                    # إصلاح خطأ الـ mediatype (قيمة افتراضية)
                    mediatype = None 
                    if node_type_str == "media-message":
                        mediatype = n.get("content", {}).get("mediaType", "")

                    # إنشاء العقدة
                    node = Node.objects.create(
                        flow=flow,
                        node_id=n.get("id"), # الـ ID الوهمي من الفرونت إند
                        node_type=node_type_str, # النوع الصحيح الآن
                        content_text=n.get("content", {}),
                        position_x=n.get("position", {}).get("x", 0),
                        position_y=n.get("position", {}).get("y", 0),
                        media_type=mediatype # يتم تمرير None أو القيمة الصحيحة
                    )
                    
                    # تخزين الرابط في الخريطة
                    node_map[n.get("id")] = node

                    # تحديد عقدة البداية
                    if node_type_str == "trigger":
                        flow.start_node = node
                        flow.save(update_fields=['start_node'])

                # ج) حفظ الروابط (Connections)
                for c in connections_data:
                    source_id = c.get("source")
                    target_id = c.get("target")
                    
                    # نستخدم الخريطة لجلب الكائنات الحقيقية
                    source_node = node_map.get(source_id)
                    target_node = node_map.get(target_id)

                    if source_node and target_node:
                        Connection.objects.create(
                            flow=flow,
                            from_node=source_node,
                            to_node=target_node,
                            data=c.get("data", {})
                        )

            log_activity('flow_created', f"Flow '{name}' created ({len(nodes_data)} nodes, {len(connections_data)} connections)", request=request, related_object=flow)
            return Response({
                "message": "Flow created successfully",
                "flow_id": flow.id,
                "nodes_count": len(nodes_data),
                "connections_count": len(connections_data)
            }, status=status.HTTP_201_CREATED)

        except Exception as e:
            print(f"❌ Error saving flow: {e}")
            return Response({"error": str(e)}, status=500)








class UpdateFlowAPIView(APIView):
    def put(self, request, pk):
        try:
            flow = Flow.objects.get(pk=pk)
        except Flow.DoesNotExist:
            return Response({"error": "Flow not found"}, status=404)

        data = request.data
        config = data.get("config", {})

        

        # 1. حذف العقد القديمة
        flow.nodes.all().delete()

        # 2. حذف الاتصالات القديمة
        flow.connections.all().delete()

        nodes_data = config.get("nodes", [])
        connections_data = config.get("connections", [])

        # 3. إنشاء nodes جديدة
        node_map = {}
        for index, node in enumerate(nodes_data):
            new_node = Node.objects.create(
                flow=flow,
                node_id=node["id"],
                type=node["type"],
                position=node.get("position", {}),
                content=node.get("content", {}),
                media_type = node.get("content", {}).get("mediaType" , "")
            )
            node_map[node["id"]] = new_node

        # 4. إنشاء connections جديدة
        for conn in connections_data:
            source = node_map.get(conn["source"])
            target = node_map.get(conn["target"])

            if source and target:
                Connection.objects.create(
                    flow=flow,
                    source=source,
                    target=target,
                    data=conn.get("data", {})
                )

        # 5. تحديث معلومات flow العامة
        flow.config = config
        flow.trigger_keywords = data.get("trigger_keywords", "")
        flow.save()
        print("flow updated ", flow)
        print("----------------------------")
        print("nodes ", flow.nodes.all())
        print("----------------------------")
        print("connections ", flow.connections.all())


        return Response({"status": "updated"})




@require_http_methods(["PUT", "POST"])
def api_update_flows(request, pk):
    """
    Update a Flow: replace nodes & connections atomically.
    Handles Trigger logic (Keywords vs Conversation Start).
    """
    try:
        if request.body:
            payload = json.loads(request.body.decode("utf-8"))
        else:
            payload = request.POST.dict()
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")
    
    # print('payload', payload) # للتبقيط

    flow = get_object_or_404(Flow, pk=pk)

    config = payload.get("config", {}) or {}
    nodes_data = config.get("nodes", []) or []
    connections_data = config.get("connections", []) or []

    if not isinstance(nodes_data, list) or not isinstance(connections_data, list):
        return HttpResponseBadRequest("Invalid config: nodes and connections must be lists")

    with transaction.atomic():
        # 1. تنظيف القديم
        flow.connections.all().delete()
        flow.nodes.all().delete()

        node_map = {}
        
        # متغير لتتبع هل وجدنا تريجر أم لا (لتحديث الفلو لاحقاً)
        found_trigger = False

        # 2. إنشاء العقد الجديدة
        for n in nodes_data:
            nid = n.get("id") or n.get("nodeId") or ""
            ntype = n.get("type") or n.get("node_type") or ""
            position = n.get("position", {}) or {}
            content = n.get("content", {}) or {}

            clean_text = ""
            clean_media = None
            clean_delay = 0
            media_type_val = None # تهيئة المتغير لتجنب الأخطاء

            if ntype == "text-message":
                clean_text = content.get("text", "")
                clean_delay = content.get("delay", 0)

            elif ntype == "media-message":
                clean_media = content.get("media_url") or content.get("url")
                clean_text = content.get("caption", "") # عادة الكابشن هو النص في الميديا
                clean_delay = content.get("delay", 0)
                media_type_val = content.get("mediaType", "image")

            elif ntype == "mixed": # إذا كنت تستخدمه
                clean_text = content.get("text", "")
                clean_media = content.get("media_url")
                clean_delay = content.get("delay", 0)

            elif ntype == "delay":
                clean_delay = content.get("duration", 0)

            elif ntype == "trigger":
                # --- منطق المحفز الجديد ---
                found_trigger = True
                match_type = content.get("match_type", "contains")
                raw_keywords = content.get("keywords", "")

                if match_type == "conversation_start":
                    # إذا كان بداية محادثة: فعل الخيار وفرغ الكلمات
                    flow.trigger_on_start = True
                    flow.trigger_keywords = ""
                    clean_text = ""
                else:
                    # إذا كان كلمات مفتاحية
                    flow.trigger_on_start = False
                    flow.trigger_keywords = raw_keywords
                    clean_text = raw_keywords
                # ---------------------------

            elif ntype == "ai-agent":
                clean_text = content.get("product_context", "") or ""
                # voice_enabled, context_source, ai_model_config stored below
            elif ntype == "follow-up":
                clean_text = content.get("caption", "") or ""
                clean_delay = 0
            elif ntype == "google-sheets":
                clean_text = content.get("label", "Export to Google Sheets") or "Export to Google Sheets"
                clean_delay = 0

            # إنشاء كائن العقدة
            create_kw = dict(
                flow=flow,
                node_id=nid,
                node_type=ntype,
                content_text=clean_text,
                content_media_url=clean_media,
                delay=clean_delay,
                position_x=position.get("x", 0),
                position_y=position.get("y", 0),
                media_type=media_type_val,
                updated_at=timezone.now(),
            )
            if ntype == "ai-agent":
                create_kw["product_context"] = content.get("product_context", "") or clean_text
                create_kw["context_source"] = content.get("context_source", "MANUAL") or "MANUAL"
                create_kw["voice_enabled"] = bool(content.get("voice_enabled", False))
                ai_cfg = content.get("ai_model_config") if isinstance(content.get("ai_model_config"), dict) else {}
                if not isinstance(ai_cfg, dict):
                    ai_cfg = {}
                pid = content.get("product_id")
                try:
                    ai_cfg["product_id"] = int(pid) if pid is not None and str(pid).strip() else None
                except (TypeError, ValueError):
                    ai_cfg["product_id"] = None
                create_kw["ai_model_config"] = ai_cfg
                create_kw["response_mode"] = content.get("response_mode") or "TEXT_ONLY"
                create_kw["node_voice_id"] = (content.get("node_voice_id") or "").strip() or None
                create_kw["node_language"] = (content.get("node_language") or "").strip() or None
                create_kw["node_gender"] = (content.get("node_gender") or "").strip() or None
                pid = content.get("persona_id")
                try:
                    create_kw["persona_id"] = int(pid) if pid is not None and int(pid) > 0 else None
                except (TypeError, ValueError):
                    create_kw["persona_id"] = None
                vs = content.get("voice_stability")
                create_kw["voice_stability"] = float(vs) if vs is not None and str(vs).replace(".", "").replace("-", "").isdigit() else None
                vsim = content.get("voice_similarity")
                create_kw["voice_similarity"] = float(vsim) if vsim is not None and str(vsim).replace(".", "").replace("-", "").isdigit() else None
                vsp = content.get("voice_speed")
                create_kw["voice_speed"] = float(vsp) if vsp is not None and str(vsp).replace(".", "").replace("-", "").isdigit() else None
            new_node = Node.objects.create(**create_kw)
            node_map[nid] = new_node

            if ntype == "follow-up":
                from discount.models import FollowUpNode
                delay_hours = content.get("delay_hours")
                try:
                    delay_hours = int(delay_hours) if delay_hours is not None else 6
                except (TypeError, ValueError):
                    delay_hours = 6
                response_type = (content.get("response_type") or "TEXT").strip().upper()
                if response_type not in ("TEXT", "AUDIO", "IMAGE", "VIDEO"):
                    response_type = "TEXT"
                ai_personalized = bool(content.get("ai_personalized", False))
                caption = (content.get("caption") or "").strip()
                FollowUpNode.objects.update_or_create(
                    node=new_node,
                    defaults={
                        "delay_hours": delay_hours,
                        "response_type": response_type,
                        "ai_personalized": ai_personalized,
                        "caption": caption,
                    },
                )

            if ntype == "google-sheets":
                from discount.models import GoogleSheetsConfig, GoogleSheetsNode
                gs_config = None
                try:
                    cfg = GoogleSheetsConfig.objects.filter(user=flow.user).first() if getattr(flow, "user", None) else None
                    if cfg:
                        gs_config = cfg
                except Exception:
                    pass
                GoogleSheetsNode.objects.update_or_create(
                    node=new_node,
                    defaults={"config": gs_config},
                )

            if ntype == "ai-agent":
                from discount.models import NodeMedia
                for m in content.get("media") or []:
                    fp = m.get("file_path") or m.get("file")
                    if not fp:
                        continue
                    file_type = m.get("file_type") or "Image"
                    if file_type not in ("Image", "Video"):
                        file_type = "Image"
                    NodeMedia.objects.create(
                        node=new_node,
                        file=fp,
                        file_type=file_type,
                        description=(m.get("description") or "")[:255],
                    )

            # تعيين عقدة البداية
            if ntype == "trigger":
                flow.start_node = new_node

        # 3. إنشاء الاتصالات
        for c in connections_data:
            src = c.get("source") or c.get("from") or c.get("from_node")
            tgt = c.get("target") or c.get("to") or c.get("to_node")
            data = c.get("data", {}) or {}

            source_node = node_map.get(src)
            target_node = node_map.get(tgt)

            if source_node and target_node:
                Connection.objects.create(
                    flow=flow,
                    from_node=source_node,
                    to_node=target_node,
                    data=data
                )

        # 4. تحديث بيانات الفلو العامة
        name = payload.get("name")
        description = payload.get("description")
        
        if name is not None:
            flow.name = name
        if description is not None:
            flow.description = description
            
        # ملاحظة: trigger_keywords تم تحديثه داخل الـ Loop أعلاه بدقة أكبر
        # بناءً على محتوى عقدة Trigger الفعلي، لذا لا نعتمد على payload.root هنا
        # إلا إذا لم نجد عقدة تريجر (حالة نادرة)
        if not found_trigger:
             # في حالة عدم وجود عقدة تريجر، نأخذ القيمة القديمة أو من البايلود كاحتياط
             kw = payload.get("trigger_keywords")
             if kw is not None:
                 flow.trigger_keywords = kw

        # حفظ الكونفيج بالكامل
        try:
            flow.config = config
        except Exception:
            pass

        flow.updated_at = timezone.now()
        flow.save()

    log_activity('flow_updated', f"Flow '{flow.name}' updated ({len(nodes_data)} nodes, {len(connections_data)} connections)", request=request, related_object=flow)
    return JsonResponse({"success": True, "status": "updated", "item": serialize_flow(flow)})


@csrf_exempt
@require_http_methods(["POST"])
def api_upload_flow_node_media(request):
    """Upload a media file for an AI Agent node. Returns file_path and file_url for inclusion in flow save payload."""
    import uuid
    from django.core.files.storage import default_storage
    try:
        flow_id = request.POST.get("flow_id")
        node_id = (request.POST.get("node_id") or "").strip()
        file_type = (request.POST.get("file_type") or "Image").strip()
        if file_type not in ("Image", "Video"):
            file_type = "Image"
        description = (request.POST.get("description") or "")[:255]
        file_obj = request.FILES.get("file")
        if not file_obj or not flow_id or not node_id:
            return JsonResponse({"error": "flow_id, node_id, and file are required"}, status=400)
        ext = os.path.splitext(getattr(file_obj, "name", "file"))[1] or (".jpg" if file_type == "Image" else ".mp4")
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", node_id)[:80]
        path = f"flow_node_media/{flow_id}/{safe_id}/{uuid.uuid4().hex}{ext}"
        default_storage.save(path, file_obj)
        try:
            url = default_storage.url(path)
        except Exception:
            url = path
        return JsonResponse({"file_path": path, "file_url": url, "file_type": file_type, "description": description})
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("api_upload_flow_node_media: %s", e)
        return JsonResponse({"error": str(e)}, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_scrape_product_url(request):
    """POST url=... Returns structured product data for AI Agent node (product_context, product_name, prices, market, additional)."""
    try:
        url = (request.POST.get("url") or request.body.decode("utf-8") or "").strip()
        if not url:
            return JsonResponse({"error": "url required"}, status=400)
        from discount.whatssapAPI.flow_utils import scrape_and_extract_product
        data = scrape_and_extract_product(url)
        return JsonResponse(data)
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception("api_scrape_product_url: %s", e)
        return JsonResponse({"error": str(e), "product_context": "", "product_name": "", "prices": "", "market": "", "additional": ""}, status=500)


def api_off_flows(request, pk):
    """
    إيقاف تدفق (تعطيل)
    """
    flow = get_object_or_404(Flow, pk=pk)
    if flow.active == False:
        flow.active = True
        flow.updated_at = timezone.now()
        flow.save()
        return JsonResponse({"success": True, "status": "activated", "item": serialize_flow(flow)})
    else:
        flow.active = False
        flow.updated_at = timezone.now()
        flow.save()
        return JsonResponse({"success": True, "status": "deactivated", "item": serialize_flow(flow)})


# ---------------------
# Persona Gallery (Flow Builder AI Node)
# ---------------------
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.core.cache import cache


def _get_channel_for_user(request, channel_id):
    """Return WhatsAppChannel if request.user can access it, else None."""
    if not channel_id or not request.user.is_authenticated:
        return None
    try:
        ch = WhatsAppChannel.objects.get(id=channel_id)
        if request.user == ch.owner or request.user.is_team_admin or request.user.is_superuser:
            return ch
    except WhatsAppChannel.DoesNotExist:
        pass
    return None


@login_required
@require_http_methods(["GET"])
def api_list_personas(request):
    """
    GET ?channel_id= optional.
    Returns standard_agents (system personas user can use), my_voices (cloned), can_use_premium.
    Basic: only standard-tier system personas. Premium: standard + premium system + own cloned.
    """
    from discount.models import VoicePersona
    from discount.services.security_check import FEATURE_PERSONA_GALLERY, FEATURE_VOICE_CLONING

    user = request.user
    can_premium = getattr(user, "is_feature_allowed", None) and user.is_feature_allowed(FEATURE_PERSONA_GALLERY)
    can_cloned = getattr(user, "is_feature_allowed", None) and user.is_feature_allowed(FEATURE_VOICE_CLONING)

    cache_key_std = f"personas_standard_{user.id}"
    cache_key_my = f"personas_my_{user.id}"
    standard = cache.get(cache_key_std)
    my_voices = cache.get(cache_key_my)
    if standard is None:
        # System personas: standard tier for all; premium tier only if can_premium
        qs = VoicePersona.objects.filter(is_system=True, owner__isnull=True).order_by("tier", "name")
        standard = []
        for p in qs:
            if p.tier == VoicePersona.TIER_STANDARD:
                standard.append({
                    "id": p.id,
                    "name": p.name,
                    "description": p.description or "",
                    "voice_id": p.voice_id,
                    "provider": getattr(p, "provider", None) or "ELEVENLABS",
                    "language_code": p.language_code,
                    "behavioral_instructions": (p.behavioral_instructions or "")[:500],
                    "tier": p.tier,
                })
            elif p.tier == VoicePersona.TIER_PREMIUM and can_premium:
                standard.append({
                    "id": p.id,
                    "name": p.name,
                    "description": p.description or "",
                    "voice_id": p.voice_id,
                    "provider": getattr(p, "provider", None) or "ELEVENLABS",
                    "language_code": p.language_code,
                    "behavioral_instructions": (p.behavioral_instructions or "")[:500],
                    "tier": p.tier,
                })
        cache.set(cache_key_std, standard, timeout=300)
    if my_voices is None:
        my_voices = []
        if can_cloned:
            for p in VoicePersona.objects.filter(owner=user).order_by("name"):
                my_voices.append({
                    "id": p.id,
                    "name": p.name,
                    "description": p.description or "",
                    "voice_id": p.voice_id,
                    "provider": getattr(p, "provider", None) or "ELEVENLABS",
                    "language_code": p.language_code,
                    "behavioral_instructions": (p.behavioral_instructions or "")[:500],
                    "tier": "cloned",
                })
        cache.set(cache_key_my, my_voices, timeout=120)
    return JsonResponse({
        "success": True,
        "standard_agents": standard,
        "my_voices": my_voices,
        "can_use_premium": can_premium,
    })


@login_required
@require_http_methods(["POST"])
def api_preview_voice(request):
    """
    POST persona_id, channel_id, text (optional).
    Returns audio/mpeg (MP3) for both ELEVENLABS and OPENAI personas. Temp file deleted after serving.
    """
    from discount.models import VoicePersona
    from discount.whatssapAPI.voice_engine import generate_audio_file

    persona_id = request.POST.get("persona_id")
    channel_id = request.POST.get("channel_id")
    text = (request.POST.get("text") or "مرحباً، أنا مساعدك الذكي.").strip()[:500]
    if not persona_id:
        return JsonResponse({"status": "error", "message": "persona_id required"}, status=400)
    channel = _get_channel_for_user(request, channel_id)
    if not channel:
        return JsonResponse({"status": "error", "message": "Channel not found"}, status=404)
    try:
        persona = VoicePersona.objects.get(id=persona_id)
    except VoicePersona.DoesNotExist:
        return JsonResponse({"status": "error", "message": "Persona not found"}, status=404)
    # Security: only system or own cloned
    if persona.owner_id and persona.owner_id != request.user.id:
        return JsonResponse({"status": "error", "message": "Not your persona"}, status=403)
    provider = (getattr(persona, "provider", None) or "ELEVENLABS").strip().upper()
    api_key = (getattr(channel, "elevenlabs_api_key", None) or "").strip() or os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if provider == "ELEVENLABS" and not api_key:
        return JsonResponse({"status": "error", "message": "ElevenLabs API key not set for this channel"}, status=400)
    # Unified MP3 via generate_audio_file (ELEVENLABS → eleven_multilingual_v2; OPENAI → tts-1 + voice_id)
    preview_settings = type("PreviewSettings", (), {
        "voice_provider": provider,
        "ai_voice_provider": provider,
        "selected_voice_id": (getattr(persona, "voice_id", None) or "").strip(),
        "voice_stability": 0.5,
        "voice_similarity": 0.75,
        "voice_speed": 1.0,
        "elevenlabs_api_key": api_key if provider == "ELEVENLABS" else "",
    })()
    path = generate_audio_file(text, preview_settings)
    if not path or not os.path.exists(path):
        return JsonResponse({"status": "error", "message": "Could not generate sample"}, status=502)
    try:
        with open(path, "rb") as f:
            content = f.read()
        from django.http import HttpResponse
        resp = HttpResponse(content, content_type="audio/mpeg")
        resp["Content-Disposition"] = 'inline; filename="persona_preview.mp3"'
        return resp
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


# ---------------------
# Google Sheets integration: Global Service Account + per-user spreadsheet_id/sheet/mapping
# ---------------------
@csrf_exempt
@require_http_methods(["GET", "PUT", "POST"])
def api_google_sheets_config(request):
    """
    GET: Return current user's config + service_account_email (from Global JSON only; never expose full credentials).
    PUT/POST: Update config. Body: spreadsheet_id?, sheet_name?, column_mapping?.
             Optional service_account_json for backward compat when global creds not set.
    """
    from django.contrib.auth.decorators import login_required
    from discount.models import GoogleSheetsConfig
    from discount.crypto import encrypt_token
    from discount.services.google_sheets_service import get_global_service_account_email, get_global_client
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    user = request.user
    if request.method == "GET":
        cfg = GoogleSheetsConfig.objects.filter(user=user).first()
        # Service account email: from service, then settings, then per-user encrypted JSON
        service_account_email = get_global_service_account_email()
        if not service_account_email:
            try:
                from django.conf import settings as django_settings
                service_account_email = (getattr(django_settings, "GOOGLE_SHEETS_SERVICE_ACCOUNT_EMAIL", None) or "").strip()
            except Exception:
                pass
        if not service_account_email and cfg and cfg.service_account_json_encrypted:
            try:
                from discount.crypto import decrypt_token
                raw = decrypt_token(cfg.service_account_json_encrypted)
                info = json.loads(raw)
                service_account_email = (info.get("client_email") or "").strip()
            except Exception:
                pass
        # Always return a string for frontend (never null)
        service_account_email = (service_account_email or "").strip()
        has_global = bool(get_global_client())
        configured = bool(
            (has_global and cfg and (cfg.spreadsheet_id or "").strip())
            or (cfg and cfg.service_account_json_encrypted)
        )
        from discount.services.google_sheets_service import SHEETS_MAPPING_AVAILABLE_FIELDS
        from discount.models import SimpleOrder
        available_fields = SHEETS_MAPPING_AVAILABLE_FIELDS
        orders_exported_count = 0
        try:
            orders_exported_count = SimpleOrder.objects.filter(
                channel__owner_id=user.id,
                sheets_export_status="success",
            ).count()
        except Exception:
            pass
        if not cfg:
            return JsonResponse({
                "spreadsheet_id": "",
                "sheet_name": "Orders",
                "column_mapping": {},
                "sheets_mapping": [],
                "available_fields": available_fields,
                "configured": False,
                "service_account_email": service_account_email,
                "orders_exported_count": orders_exported_count,
            })
        return JsonResponse({
            "spreadsheet_id": (cfg.spreadsheet_id or ""),
            "sheet_name": (cfg.sheet_name or "Orders"),
            "column_mapping": cfg.column_mapping if isinstance(cfg.column_mapping, dict) else {},
            "sheets_mapping": cfg.sheets_mapping if isinstance(cfg.sheets_mapping, list) else [],
            "available_fields": available_fields,
            "configured": configured,
            "service_account_email": service_account_email,
            "orders_exported_count": orders_exported_count,
        })
    # PUT or POST: update config
    try:
        if request.content_type and "application/json" in request.content_type:
            data = json.loads(request.body.decode("utf-8") or "{}")
        else:
            data = request.POST.dict()
    except Exception:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    cfg, _ = GoogleSheetsConfig.objects.get_or_create(user=user, defaults={"spreadsheet_id": "", "sheet_name": "Orders"})
    if "spreadsheet_id" in data:
        cfg.spreadsheet_id = (data.get("spreadsheet_id") or "").strip()
    if "sheet_name" in data:
        cfg.sheet_name = (data.get("sheet_name") or "Orders").strip() or "Orders"
    if "column_mapping" in data:
        cm = data.get("column_mapping")
        cfg.column_mapping = cm if isinstance(cm, dict) else {}
    if "sheets_mapping" in data:
        sm = data.get("sheets_mapping")
        cfg.sheets_mapping = sm if isinstance(sm, list) else []
    if "service_account_json" in data:
        raw = data.get("service_account_json")
        if raw is None or raw == "":
            cfg.service_account_json_encrypted = None
        else:
            try:
                if isinstance(raw, dict):
                    raw = json.dumps(raw)
                elif not isinstance(raw, str):
                    raw = str(raw)
                cfg.service_account_json_encrypted = encrypt_token(raw)
            except Exception as e:
                return JsonResponse({"error": "Failed to encrypt credentials: " + str(e)}, status=400)
    cfg.updated_at = timezone.now()
    cfg.save()
    return JsonResponse({
        "success": True,
        "spreadsheet_id": (cfg.spreadsheet_id or ""),
        "sheet_name": (cfg.sheet_name or "Orders"),
        "column_mapping": cfg.column_mapping,
        "sheets_mapping": cfg.sheets_mapping if isinstance(cfg.sheets_mapping, list) else [],
        "configured": bool(cfg.service_account_json_encrypted),
    })


@csrf_exempt
@require_http_methods(["GET"])
def api_google_sheets_service_email(request):
    """
    GET: Return the Service Account client_email only (from Global JSON; never expose credentials).
         Used so the merchant can share their sheet with this email.
    """
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"error": "Authentication required"}, status=401)
    from discount.services.google_sheets_service import get_global_service_account_email, get_global_client
    email = get_global_service_account_email()
    if not email:
        try:
            from django.conf import settings as django_settings
            email = (getattr(django_settings, "GOOGLE_SHEETS_SERVICE_ACCOUNT_EMAIL", None) or "").strip()
        except Exception:
            pass
    if not email:
        from discount.models import GoogleSheetsConfig
        from discount.crypto import decrypt_token
        cfg = GoogleSheetsConfig.objects.filter(user=request.user).first()
        if cfg and cfg.service_account_json_encrypted:
            try:
                raw = decrypt_token(cfg.service_account_json_encrypted)
                info = json.loads(raw)
                email = (info.get("client_email") or "").strip()
            except Exception:
                pass
    return JsonResponse({"service_account_email": (email or "").strip(), "configured": bool(get_global_client() or email)})


@csrf_exempt
@require_http_methods(["POST"])
def api_google_sheets_test_connection(request):
    """
    POST: Test connection using Global Service Account (or user credentials).
    Body: spreadsheet_id (required for test). On success, saves spreadsheet_id to user's config.
    Returns { "success": true/false, "message": "..." }. Friendly message on permission denied.
    """
    from django.contrib.auth.decorators import login_required
    from discount.models import GoogleSheetsConfig
    from discount.services.google_sheets_service import test_connection
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return JsonResponse({"success": False, "message": "Authentication required"}, status=401)
    try:
        if request.content_type and "application/json" in request.content_type:
            data = json.loads(request.body.decode("utf-8") or "{}")
        else:
            data = request.POST.dict()
        spreadsheet_id = (data.get("spreadsheet_id") or "").strip()
    except Exception:
        spreadsheet_id = ""
    if not spreadsheet_id:
        return JsonResponse({"success": False, "message": "Spreadsheet ID is required."})
    cfg, _ = GoogleSheetsConfig.objects.get_or_create(user=request.user, defaults={"spreadsheet_id": "", "sheet_name": "Orders"})
    # Use a temp config with the spreadsheet_id to test (credentials come from global or cfg)
    class _TestConfig:
        pass
    t = _TestConfig()
    t.spreadsheet_id = spreadsheet_id
    t.sheet_name = getattr(cfg, "sheet_name", "Orders") or "Orders"
    t.service_account_json_encrypted = getattr(cfg, "service_account_json_encrypted", None)
    t.column_mapping = getattr(cfg, "column_mapping", None)
    try:
        ok, msg = test_connection(t)
    except Exception as e:
        ok, msg = False, str(e)
    if ok:
        cfg.spreadsheet_id = spreadsheet_id
        cfg.updated_at = timezone.now()
        cfg.save()
    return JsonResponse({"success": ok, "message": msg or ("Connection successful" if ok else "Connection failed")})







    
 