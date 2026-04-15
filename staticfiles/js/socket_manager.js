const ChatSocket = {
    socket: null,
    
    // 1. دالة تهيئة الاتصال (تستدعى مرة واحدة عند تحميل الموقع)
    init: function(object) {
        const wsprotocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const url = wsprotocol + '://' + window.location.host + '/chat/stream/'; 
        this.socket = new WebSocket(url);

        // ربط الأحداث
        this.socket.onopen = () => {};
        this.socket.onclose = () => {
            
            setTimeout(() => ChatSocket.init(), 2000); // ✅ صحيح
                
        }
        
        // هنا "الموزع" الذي يستقبل الرسائل
        this.socket.onmessage = (e) => {
            const data = JSON.parse(e.data);
            this.handleIncomingMessage(data);
            
        };
    },




    // 2. دالة الإرسال العامة (Global Sender)
    // أي دالة أخرى في مشروعك ستستخدم هذه الدالة للإرسال
    send: function(type, payload) {
        if (this.socket.readyState === WebSocket.OPEN) {
            try {
                this.socket.send(JSON.stringify({
                    'type': type,       // مثلاً: 'new_message'
                    'payload': payload  // البيانات الفعلية
                }));
                return true;
            } catch (e) {
                console.error("Socket send failed:", e);
                return false;
            }
        } else {
            console.error("Socket is not open.");
            return false;
        }
    },



    
 handleIncomingMessage: function(data) {
    // Direct reply from WebhookConsumer (not group broadcast): uses `type`, not `data_type`
    if (data.type === 'send_result') {
        if (data.status && data.status !== 200) {
            const p = data.payload || {};
            const msg = (p.error || p.details || p.message || JSON.stringify(p)).toString().substring(0, 900);
            console.error('send_result failed:', data);
            if (typeof window.showSendErrorchat === 'function') {
                window.showSendErrorchat({ error: 'Send failed', reason: msg }, {});
            } else {
                alert('Send failed: ' + msg);
            }
        }
        return;
    }
    if (data.type === 'error' && data.message && !data.data_type) {
        console.error('WebSocket error:', data.message);
        return;
    }

    const type = data.data_type;
    

    switch (type) {

    case 'error': {
        const p = data.payload || data;
        const msg = (p.error || p.details || p.message || 'Unknown error').toString().substring(0, 900);
        console.error('Socket error event:', p);
        if (typeof window.showSendErrorchat === 'function') {
            window.showSendErrorchat({ error: 'Send failed', reason: msg }, {});
        } else {
            alert(msg);
        }
        break;
    }

        
    case 'user_status_change': 
    if ( typeof window.updateUserStatusUI === 'function') {
        window.updateUserStatusUI(data.user_id, data.status);
    }
    break;

        case 'collision_update': {
            if (typeof window.handleCollisionUpdate === 'function') {
                window.handleCollisionUpdate(data.payload);
            }

            break;
        }
        case 'note_message':{
            const payload = data.payload;
            
             const activePhone = (typeof window.getCurrentChatPhone === 'function') 
                                 ? window.getCurrentChatPhone() 
                                 : null;
             
             // تنظيف الأرقام للمقارنة
             const incomingPhone = payload.contact.phone.replace(/\D/g, '');
             const currentActive = activePhone ? activePhone.replace(/\D/g, '') : '';
 
             if (currentActive && currentActive === incomingPhone) {
                 // 2. عرض الرسالة في الشات
                 if (typeof window.appendMessagesws === 'function') {
                    
                     window.appendMessagesws([payload]); 
                 }
                 
                 // 3. التمرير للأسفل لرؤية السجل الجديد
                 const chatContainer = document.getElementById('chat_messages_area');
                 if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
             }
  
             break;
          
        }


        case 'log_message_received': {
            const payload = data.payload;
            
            const activePhone = (typeof window.getCurrentChatPhone === 'function') 
                                ? window.getCurrentChatPhone() 
                                : null;
            
            // تنظيف الأرقام للمقارنة
            const incomingPhone = payload.contact.phone.replace(/\D/g, '');
            const currentActive = activePhone ? activePhone.replace(/\D/g, '') : '';

            if (currentActive && currentActive === incomingPhone) {
                // 2. عرض الرسالة في الشات
                if (typeof window.appendMessagesws === 'function') {
                   
                    window.appendMessagesws([payload.message]); 
                }
                
                // 3. التمرير للأسفل لرؤية السجل الجديد
                const chatContainer = document.getElementById('chat_messages_area');
                if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
            }
 
            break;
        }



        
        case "finished": {
            const payload = data.payload;
            // 1. تحديد المستلم
            const recipientPhone = payload.to || payload.phone || '';
            
            // 2. تحديث الشات (الكود السابق الذي يمنع التداخل)
            const activePhone = (typeof window.getCurrentChatPhone === 'function') ? window.getCurrentChatPhone() : null;
            const cleanRecipient = recipientPhone.toString().replace(/\D/g, '');
            const cleanActive = activePhone ? activePhone.toString().replace(/\D/g, '') : '';

            // عرض الرسالة في الشات إذا كنا فاتحين نفس المحادثة
            if (cleanActive && cleanActive === cleanRecipient) {
                const formattedMsg = {
                    id: payload.saved_message_id, 
                    body: payload.body,
                    type: payload.media_type || 'text',
                    url: payload.media_url || payload.url || '', 
                    time: new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}),
                    fromMe: true, 
                    status: 'sent' 
                };
                if (typeof window.appendMessagesws === 'function') {
                    window.appendMessagesws([formattedMsg]); 
                }
                const chatContainer = document.getElementById('chat_messages_area');
                if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
            }

            
            const currentItem = document.querySelector(`.cls3741_contact_item[data-phone="${cleanRecipient}"]`);
            let currentName = recipientPhone;
            let currentPic = null; // سيتم استخدام الافتراضي إذا كان null

            if (currentItem) {
                currentName = currentItem.getAttribute('data-name') || recipientPhone;
                const img = currentItem.querySelector('img');
                if (img) currentPic = img.src;
            }

            // ب) تجهيز نص المختصر (Snippet)
            let snippetText = payload.body;
            if (!snippetText && payload.media_type) {
                if (payload.media_type === 'audio') snippetText = '🎤 مقطع صوتي';
                else if (payload.media_type === 'image') snippetText = '📷 صورة';
                else snippetText = '📁 ملف';
            }

            // ج) بناء كائن التحديث
            const sidebarUpdateData = {
                phone: recipientPhone,
                name: currentName,      // نحافظ على الاسم القديم
                profile_picture: currentPic, // نحافظ على الصورة القديمة
                snippet: snippetText,
                timestamp: 'Now',
                
                unread: 0,       // 🔥 صفرنا العداد (سيختفي البادج الأخضر)
                fromMe: true,    // 🔥 هذا سيجعل النص رمادياً عادياً (ليس أخضر)
                last_status: 'sent' // سيظهر علامة صح واحدة
            };

            // د) استدعاء دالة التحديث
            if (typeof window.updateContactItemSingle === 'function') {
                window.updateContactItemSingle(sidebarUpdateData);
            }

            break;
        }

        case 'handover':
        case 'handover_new_message': {
            const payload = data.payload || {};
            const channelId = payload.channel_id != null ? String(payload.channel_id) : null;
            const customerPhone = (payload.customer_phone || '').toString().replace(/\D/g, '');
            const reason = payload.reason || 'Needs Human Action';
            const currentChannelId = (typeof window.getCurrentChannelId === 'function' ? window.getCurrentChannelId() : null) || window._activeChannelId || (window.currentChannelId != null ? String(window.currentChannelId) : null);
            const channelMatch = !channelId || !currentChannelId || (String(currentChannelId) === String(channelId));

            if (customerPhone && channelMatch) {
                const activePhone = (typeof window.getCurrentChatPhone === 'function') ? window.getCurrentChatPhone() : null;
                const cleanActive = activePhone ? activePhone.toString().replace(/\D/g, '') : '';
                if (cleanActive === customerPhone && typeof window.dismissSendErrorBannerForChat === 'function') {
                    window.dismissSendErrorBannerForChat(payload.customer_phone || customerPhone);
                }
                if (cleanActive === customerPhone && typeof window.updateHitlUI === 'function') {
                    window.updateHitlUI(activePhone);
                    var hitlBadge = document.getElementById('hitl_badge');
                    if (hitlBadge) hitlBadge.title = reason;
                }
                if (typeof window.setContactNeedsHuman === 'function') {
                    window.setContactNeedsHuman(payload.customer_phone || customerPhone, true, reason, channelId);
                }
            }
            break;
        }

        case 'message_status_update':{
            const payload = data.payload;
            const msgStatusIcon = document.querySelector(`[data-msg-id="${data.payload.message_id}"] .cls3741_msg_status`);
            
            if (msgStatusIcon) {
        const newIconSVG = window.getStatusIconHTML(data.payload.status);
        msgStatusIcon.innerHTML = newIconSVG;
            }
       
            break;
 }




        case  'existing_customer_message':{
            const payload = data.payload;
            const msgChannelId = String(payload.message?.channel_id || '');
            const curChannelId = String(
                (typeof window.getCurrentChannelId === 'function' ? window.getCurrentChannelId() : null)
                || window._activeChannelId || ''
            );
            const channelMatch = !curChannelId || !msgChannelId || (curChannelId === msgChannelId);
            if (channelMatch && typeof window.updateContactItemSingle === 'function') {
                window.updateContactItemSingle(payload.message);
            }
            break;
        }

        case 'update_sidebar_contact': {
            const contactData = data.payload;
            const sidebarChannelId = String(contactData.channel_id || '');
            const curCh = String(
                (typeof window.getCurrentChannelId === 'function' ? window.getCurrentChannelId() : null)
                || window._activeChannelId || ''
            );
            const chMatch = !curCh || !sidebarChannelId || (curCh === sidebarChannelId);

            if (chMatch && typeof window.updateContactItemSingle === 'function') {
                const existingItem = document.querySelector(`.cls3741_contact_item[data-phone="${contactData.phone}"]`);
                if (existingItem) {
                    if (!contactData.name || contactData.name === contactData.phone) {
                        contactData.name = existingItem.getAttribute('data-name');
                    }
                    const img = existingItem.querySelector('img');
                    if (img) {
                        contactData.profile_picture = img.src;
                    }
                }
                window.updateContactItemSingle(contactData);
            }
            break;
        }


        case 'new_message_received': {
            const payload = data.payload;
            const incomingPhone = payload.contact.phone;
            const incomingChannelId = String(payload.contact.channel_id || payload.message.channel_id || '');
            if (!payload.message) return;

            let messageText = "";

            if (payload.message.type == 'text') {
                messageText = payload.message.body;  
            } else {
                if (payload.message.type == 'image') {
                    messageText = "Image";
                }  
                if (payload.message.type == 'video') {
                    messageText = "Video";
                }   
                if (payload.message.type == 'audio') {
                    messageText = "Audio";
                }
            }

            // Determine the currently active channel
            const viewingChannelId = String(
                (typeof window.getCurrentChannelId === 'function' ? window.getCurrentChannelId() : null)
                || window._activeChannelId
                || ''
            );

            // Check if this message belongs to the channel the user is currently viewing
            const isCurrentChannel = !viewingChannelId || !incomingChannelId || (viewingChannelId === incomingChannelId);

            if (typeof window.highlightOrderRow === 'function') {
                window.highlightOrderRow(payload.contact.phone);
            }

            // Only update the sidebar contact list if the message is for the active channel
            if (isCurrentChannel) {
                if (typeof window.updateContactItemSingle === 'function') {
                    window.updateContactItemSingle(payload.contact, payload.message);
                }
            }

            const activePhone = (typeof window.getCurrentChatPhone === 'function') 
                                ? window.getCurrentChatPhone() 
                                : null;

            // Only append the message to the chat area if same channel AND same phone
            if (isCurrentChannel && activePhone && (activePhone == payload.contact.phone)) { 
                if (typeof window.appendMessagesws === 'function') {
                    window.appendMessagesws([payload.message]); 
                }
                if (payload.message && !payload.message.fromMe && typeof window.dismissSendErrorBannerForChat === 'function') {
                    window.dismissSendErrorBannerForChat(payload.contact.phone);
                }
            }

            if (typeof window.updateinterface === 'function') window.updateinterface(payload);

            // Update the unread dot on the channel icon in the sidebar for OTHER channels
            if (!isCurrentChannel && incomingChannelId) {
                const channelBtn = document.querySelector(`.workspace-item[data-channel-id="${incomingChannelId}"]`);
                if (channelBtn) {
                    let dot = channelBtn.querySelector('.unread-dot');
                    if (!dot) {
                        dot = document.createElement('span');
                        dot.className = 'unread-dot';
                        channelBtn.appendChild(dot);
                    }
                }
            }
            
            const cleanIncoming = incomingPhone.replace(/\D/g, '');
            const cleanActive = activePhone ? activePhone.replace(/\D/g, '') : '';

            if (cleanIncoming !== cleanActive) {
                if (typeof window.showNotification === 'function') {
                    window.showNotification(
                        `${payload.contact.name || incomingPhone}`,
                        messageText,
                        function() {
                            // On notification click: switch to the correct channel first, then open the chat
                            if (incomingChannelId && viewingChannelId !== incomingChannelId) {
                                if (typeof window.switchChannel === 'function') {
                                    window.switchChannel(incomingChannelId).then(function() {
                                        if (window.__chatSelectPhone) {
                                            window.__chatSelectPhone(incomingPhone, payload.contact.name);
                                        }
                                    });
                                }
                            } else {
                                if (window.__chatSelectPhone) {
                                    window.__chatSelectPhone(incomingPhone, payload.contact.name);
                                }
                            }
                        }
                    );
                }
            } else {
            }
            break;
        }


 
     
    


        default:
            console.warn("Unknown message type:", type);
    }
}
};

// جعل الكائن متاحاً للنافذة بالكامل (Global Scope)
window.ChatSocket = ChatSocket;