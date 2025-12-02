// document.addEventListener("DOMContentLoaded", function() {
//   window.API_URLS = {
//     send: "{% url 'send_message' %}",
//     upload: "{% url 'upload_media' %}",   /* أنشئ هذا الendpoint في Django أو استخدم نفس send إذا لم تملكه */
//     messages: "{% url 'get_messages' %}"
//   };  

// (function(){
//   // العناصر
//   const contactsListEl = document.getElementById('cls3741_contacts_list');
//   const messagesArea = document.getElementById('cls3741_messages_area');
//   const inputBody = document.getElementById('body');
//   const sendBtn = document.getElementById('cls3741_send_btn');
//   const imageInput = document.getElementById('image_upload');
//   const videoInput = document.getElementById('video_upload');
//   const imageBtn = document.getElementById('image_btn');
//   const videoBtn = document.getElementById('video_btn');
//   const audioRecordBtn = document.getElementById('audio_record_btn');
//   const mediaPreviewArea = document.getElementById('media_preview_area');

//   let currentPhone = null;
//   let lastMessageId = 0;
//   let contactsSnapshot = '';
//   let pollInterval = 50000; // تقليل الفترة للمزيد من التحديثات السريعة
//   let pollTimer = null;
//   let contactPollCounter = 0;

//   let queuedFile = null;
//   let queuedFileType = null;

//   // حالة التسجيل الصوتي
//   let mediaRecorder = null;
//   let audioBlobs = [];

//   // دالة لإنشاء أيقونة تحميل جميلة
//   function createLoadingSpinner() {
//     const spinner = document.createElement('div');
//     spinner.className = 'cls3741_loading_spinner';
//     spinner.style.cssText = `
//       width: 40px;
//       height: 40px;
//       border: 3px solid #f3f4f6;
//       border-top: 3px solid #000000;
//       border-radius: 50%;
//       animation: spin 1s linear infinite;
//       margin: 20px auto;
//     `;
//     return spinner;
//   }

//   function createLoadingMessage() {
//     const container = document.createElement('div');
//     container.style.cssText = `
//       display: flex;
//       flex-direction: column;
//       align-items: center;
//       justify-content: center;
//       padding: 40px 20px;
//       color: var(--text-secondary);
//     `;
    
//     container.innerHTML = `
//       ${createLoadingSpinner().outerHTML}
//       <div style="margin-top: 16px; font-size: 14px;">جاري تحميل المحادثة...</div>
//     `;
    
//     return container;
//   }

//   function getCsrfToken(){
//     const tokenEl = document.querySelector('[name=csrfmiddlewaretoken]');
//     return tokenEl ? tokenEl.value : '';
//   }

//   function escapeHtml(s){
//     return (s||'').toString()
//       .replace(/&/g,'&amp;')
//       .replace(/</g,'&lt;')
//       .replace(/>/g,'&gt;')
//       .replace(/"/g,'&quot;')
//       .replace(/'/g,'&#039;');
//   }

//   function scrollToBottom(force=false){
//     if(!messagesArea) return;
//     const nearBottom = messagesArea.scrollTop + messagesArea.clientHeight >= messagesArea.scrollHeight - 80;
//     if(force || nearBottom) {
//       messagesArea.scrollTop = messagesArea.scrollHeight;
//     }
//   }

//   function existsMsgId(id){
//     if(!id) return false;
//     return !!messagesArea.querySelector(`[data-msg-id="${id}"]`);
//   }

//   // دالة محسنة لعرض حالة الرسالة
//   function getMessageStatusIcon(status, timestamp) {
//     const icons = {
//       'sent': '✓',
//       'delivered': '✓✓',
//       'read': '✓✓', // باللون الأزرق عادة
//       'failed': '!'
//     };
    
//     const statusText = {
//       'sent': 'تم الإرسال',
//       'delivered': 'تم التسليم',
//       'read': 'تم القراءة',
//       'failed': 'فشل الإرسال'
//     };
    
//     const icon = icons[status] || '✓';
//     const text = statusText[status] || 'تم الإرسال';
    
//     return `<span class="cls3741_msg_status" data-status="${status}" title="${text} ${timestamp}">${icon}</span>`;
//   }

//   // دالة محسنة لإنشاء عقدة الرسالة
//   function makeMessageNode(m){
//     const isMe = !!m.fromMe;
//     const wrapper = document.createElement('div');
//     wrapper.className = 'cls3741_msg_bubble' + (isMe ? ' me' : '');
//     if(m.id) wrapper.dataset.msgId = m.id;

//     const timeHtml = `<span class="cls3741_msg_time">${escapeHtml(m.time)}</span>`;
//     const statusHtml = isMe ? getMessageStatusIcon(m.status || 'sent', m.time) : '';

//     if(m.type === 'audio'){
//       const html = `
//         <div class="audio-message ${isMe ? 'fromMe' : 'fromThem'}" role="group" aria-label="audio message">
//           <button class="audio-play" type="button" aria-label="Play audio">▶</button>
//           <div class="audio-progress"><div class="bar"></div></div>
//           <span class="audio-time">0:00</span>
//           <audio preload="metadata" style="display:none">
//             <source src="${escapeHtml(m.url || '')}" type="${escapeHtml(m.mime || 'audio/ogg')}">
//           </audio>
//         </div>
//         <div class="cls3741_msg_footer">
//           ${timeHtml}
//           ${statusHtml}
//         </div>
//       `;
//       wrapper.innerHTML = html;
      
//       // إضافة تأثير الظهور بعد إنشاء العنصر
//       setTimeout(() => {
//         const audioMessage = wrapper.querySelector('.audio-message');
//         if (audioMessage) {
//           audioMessage.classList.add('show');
//         }
//       }, 50);
      
//     } else if(m.type === 'image'){
//       wrapper.innerHTML = `
//         <img class="cls3741_media_image" src="${escapeHtml(m.url || '')}" alt="image" loading="lazy" />
//         <div class="cls3741_msg_footer">
//           ${timeHtml}
//           ${statusHtml}
//         </div>
//       `;
//     } else if(m.type === 'video'){
//       wrapper.innerHTML = `
//         <video class="cls3741_media_video" controls preload="metadata">
//           <source src="${escapeHtml(m.url || '')}" type="${escapeHtml(m.mime || 'video/mp4')}">
//         </video>
//         <div class="cls3741_msg_footer">
//           ${timeHtml}
//           ${statusHtml}
//         </div>
//       `;
//     } else {
//       wrapper.innerHTML = `
//         <div class="cls3741_text">${escapeHtml(m.body || '')}</div>
//         <div class="cls3741_msg_footer">
//           ${timeHtml}
//           ${statusHtml}
//         </div>
//       `;
//     }
    
//     // إضافة تأثير ظهور سلس للرسائل الجديدة
//     wrapper.style.opacity = '0';
//     wrapper.style.transform = 'translateY(10px)';
//     wrapper.style.transition = 'all 0.3s ease';
    
//     setTimeout(() => {
//       wrapper.style.opacity = '1';
//       wrapper.style.transform = 'translateY(0)';
//     }, 50);
    
//     return wrapper;
// }



//   // دالة محسنة لإرفاق معالجات الصوت
//  function attachAudioHandlers(container){
//     const wrapper = container.querySelector('.audio-message');
//     if(!wrapper) return;
//     const audioEl = wrapper.querySelector('audio');
//     const playBtn = wrapper.querySelector('.audio-play');
//     const bar = wrapper.querySelector('.bar');
//     const timeEl = wrapper.querySelector('.audio-time');
//     if(!audioEl || !playBtn) return;

//     const fmt = (s) => {
//         if (!isFinite(s) || s <= 0) return '0:00';
//         const mm = Math.floor(s / 60), ss = Math.floor(s % 60).toString().padStart(2,'0');
//         return `${mm}:${ss}`;
//     };

//     function pauseOtherAndRegister(){
//         if(window.__activeAudio && window.__activeAudio !== audioEl){
//             try{
//                 window.__activeAudio.pause();
//                 if(window.__activePlayBtn) {
//                     window.__activePlayBtn.textContent = '▶';
//                     window.__activePlayBtn.style.transform = 'scale(1)';
//                 }
//                 if(window.__activeBar) window.__activeBar.style.width = '0%';
//             }catch(e){}
//         }
//         window.__activeAudio = audioEl;
//         window.__activePlayBtn = playBtn;
//         window.__activeBar = bar;
//         window.__activeTime = timeEl;
//     }

//     playBtn.addEventListener('click', ()=>{
//         if(audioEl.paused){
//             pauseOtherAndRegister();
//             audioEl.play().catch(()=>{});
//             playBtn.textContent = '⏸';
//             playBtn.style.transform = 'scale(1.05)';
//         } else {
//             audioEl.pause();
//             playBtn.textContent = '▶';
//             playBtn.style.transform = 'scale(1)';
//         }
//     });

//     audioEl.addEventListener('timeupdate', ()=>{
//         const total = audioEl.duration;
//         const curr = audioEl.currentTime;
//         if(bar && isFinite(total) && total > 0){
//             bar.style.width = `${(curr/total)*100}%`;
//         }
//         if(timeEl) timeEl.textContent = fmt(curr);
//     });

//     audioEl.addEventListener('ended', ()=>{
//         playBtn.textContent = '▶';
//         playBtn.style.transform = 'scale(1)';
//         if(bar) bar.style.width = '0%';
//         if(timeEl) timeEl.textContent = fmt(0);
//         if(window.__activeAudio === audioEl){
//             window.__activeAudio = null;
//             window.__activePlayBtn = null;
//             window.__activeBar = null;
//             window.__activeTime = null;
//         }
//     });

//     // إضافة تأثير hover
//     wrapper.addEventListener('mouseenter', () => {
//         wrapper.style.transform = 'translateY(-1px)';
//         wrapper.style.boxShadow = '0 4px 8px rgba(0,0,0,0.1)';
//     });

//     wrapper.addEventListener('mouseleave', () => {
//         wrapper.style.transform = 'translateY(0)';
//         wrapper.style.boxShadow = '0 2px 4px rgba(0,0,0,0.05)';
//     });
// }
//   // دالة محسنة لإضافة الرسائل
//   function appendMessages(msgArray){
//     if (!msgArray || !Array.isArray(msgArray)) return;
    
//     msgArray.sort((a,b)=> (a.id||0) - (b.id||0));
//     let hasNewMessages = false;
    
//     for(const m of msgArray){
//       if(m.id && existsMsgId(m.id)) {
//         if(m.id > (lastMessageId||0)) lastMessageId = m.id;
//         continue;
//       }
      
//       const node = makeMessageNode(m);
//       messagesArea.appendChild(node);
//       if(m.type === 'audio') attachAudioHandlers(node);
//       if(m.id && m.id > (lastMessageId||0)) lastMessageId = m.id;
//       hasNewMessages = true;
//     }
    
//     if (hasNewMessages) {
//       scrollToBottom(true);
//     }
//   }




//   // دالة محسنة لجلب الرسائل
//   async function fetchMessagesForCurrent(){
//     if(!currentPhone) return;
    
//     const url = `{% url 'get_messages' %}?phone=${encodeURIComponent(currentPhone)}&since_id=${encodeURIComponent(lastMessageId||0)}`;
//     try{
//       const res = await fetch(url, { 
//         cache: 'no-store', 
//         headers: { 'Accept': 'application/json' }
//       });
      
//       if(!res.ok) return;
      
//       const data = await res.json();
//       const msgs = data.messages || [];
      
//       if(!Array.isArray(msgs) || msgs.length === 0) return;
      
//       appendMessages(msgs);
      
//       // تحديث حالة الرسائل المقروءة
//       updateMessageStatuses(msgs);
      
//     }catch(e){ 
//       console.error('fetchMessagesForCurrent', e); 
//     }
//   }

//   // دالة جديدة لتحديث حالات الرسائل
//   function updateMessageStatuses(messages) {
//     messages.forEach(msg => {
//       if (msg.id && msg.status) {
//         const existingMsg = messagesArea.querySelector(`[data-msg-id="${msg.id}"]`);
//         if (existingMsg) {
//           const statusElement = existingMsg.querySelector('.cls3741_msg_status');
//           if (statusElement) {
//             statusElement.innerHTML = getMessageStatusIcon(msg.status, msg.time);
//             statusElement.dataset.status = msg.status;
//           }
//         }
//       }
//     });
//   }

//   // دالة محسنة لجلب جهات الاتصال
//   async function fetchContactsAndUpdateUI(){
//     // const url = "{% url 'api_contacts' %}";
//     const url = "whatssapAPI/api/contacts/"
//     try{
//       const res = await fetch("{% url 'api_contacts' %}", { 
//         // cache: 'no-store', 
//         headers: { 'Accept': 'application/json' }
//       });
      
//       if(!res.ok) return;
      
//       const data = await res.json();
//       const contacts = data.contacts || [];
//       const snapshot = JSON.stringify(contacts.map(c => [c.phone, c.last_id, c.unread]));
      
//       if(snapshot === contactsSnapshot) return;
//       contactsSnapshot = snapshot;

//       const frag = document.createDocumentFragment();
//       contacts.forEach(c => {
//         let item = contactsListEl.querySelector(`.cls3741_contact_item[data-phone="${c.phone}"]`);
//         if (!item) {
//           item = document.createElement('div');
//           item.className = 'cls3741_contact_item';
//           item.setAttribute('data-phone', c.phone);
//           item.setAttribute('data-name', c.name || c.phone);
//         }
        
//         const initial = (c.name || c.phone || '?').trim().charAt(0).toUpperCase();
//         const unreadBadge = (c.unread && c.unread > 0) ? 
//           `<div class="cls3741_contact_badge">${c.unread}</div>` : 
//           `<div class="cls3741_contact_badge" style="opacity:0">—</div>`;
          
//         item.innerHTML = `
//           <div class="cls3741_contact_avatar">${escapeHtml(initial)}</div>
//           <div class="cls3741_contact_meta">
//             <div class="cls3741_contact_name">${escapeHtml(c.name || c.phone)}</div>
//             <div class="cls3741_contact_snippet">${escapeHtml(c.snippet || '')}</div>
//           </div>
//           ${unreadBadge}
//         `;
//         frag.appendChild(item);
//       });

//       contactsListEl.innerHTML = '';
//       contactsListEl.appendChild(frag);
      
//     }catch(e){ 
//       console.error('fetchContactsAndUpdateUI', e); 
//     }
//   }

//   // دالة محسنة لاختيار جهة اتصال
//   function onContactSelected(el){
//     const phone = el.getAttribute('data-phone');
//     const name = el.getAttribute('data-name') || null;
//     if(!phone) return;
    
//     currentPhone = phone.replace(/^\+/, '').replace(/\s+/g,'');
//     lastMessageId = 0;

//     // تحديث واجهة المستخدم
//     const avatarEl = document.getElementById('cls3741_active_avatar');
//     if (avatarEl) avatarEl.textContent = (name||phone).trim().charAt(0).toUpperCase();
    
//     const nameEl = document.getElementById('cls3741_active_name');
//     if (nameEl) nameEl.textContent = name || phone;
    
//     const userAvatarEl = document.getElementById('cls3741_user_avatar');
//     if (userAvatarEl) userAvatarEl.textContent = (name||phone).trim().charAt(0).toUpperCase();
    
//     const userNameEl = document.getElementById('cls3741_user_name');
//     if (userNameEl) userNameEl.textContent = name || phone;
    
//     const userPhoneEl = document.getElementById('cls3741_user_phone');
//     if (userPhoneEl) userPhoneEl.textContent = '+' + currentPhone;

//     // إظهار رسالة تحميل محسنة
//     messagesArea.innerHTML = '';
//     messagesArea.appendChild(createLoadingMessage());
    
//     fetchMessagesForCurrent().then(()=>{
//       const item = contactsListEl.querySelector(`.cls3741_contact_item[data-phone="${phone}"]`);
//       if(item){
//         const badge = item.querySelector('.cls3741_contact_badge');
//         if(badge) badge.textContent = '—';
//         badge.style.opacity = '0.5';
//       }
//     });
//   }

//   // الباقي من الدوال (إدارة الملفات، التسجيل، الإرسال) تبقى كما هي مع تحسينات طفيفة
//   // ... [الكود السابق لإدارة الملفات والتسجيل]

//   // ربط الأحداث
//   contactsListEl?.addEventListener('click', function(e){
//     let el = e.target;
//     while(el && !el.classList.contains('cls3741_contact_item')) el = el.parentElement;
//     if(el) onContactSelected(el);
//   });

  
//   async function pollLoop(){
//     try{
//       if(currentPhone) await fetchMessagesForCurrent();
//       contactPollCounter = (contactPollCounter + 1) % 3;
//       if(contactPollCounter === 0) await fetchContactsAndUpdateUI();
//     }catch(e){
//       console.error('pollLoop', e);
//     } finally {
//       pollTimer = setTimeout(pollLoop, pollInterval);
//     }
//   }

//   // التهيئة
//   fetchContactsAndUpdateUI();
//   pollLoop();

//   window.__chatSelectPhone = function(phone, name){
//     const normalized = (phone||'').replace(/^\+/, '').replace(/\s+/g,'');
//     const item = contactsListEl.querySelector(`.cls3741_contact_item[data-phone="${normalized}"]`);
//     if(item){ 
//       item.click(); 
//       return; 
//     }
    
//     currentPhone = normalized;
//     lastMessageId = 0;
//     const userPhoneEl = document.getElementById('cls3741_user_phone');
//     if (userPhoneEl) userPhoneEl.textContent = '+' + normalized;
    
//     // إظهار رسالة تحميل
//     messagesArea.innerHTML = '';
//     messagesArea.appendChild(createLoadingMessage());
    
//     fetchMessagesForCurrent();
//     fetchContactsAndUpdateUI();
//   };

//   // إضافة CSS إضافي للحالات والتحميل
//   const additionalStyles = `
//     <style>
//       .cls3741_msg_footer {
//         display: flex;
//         align-items: center;
//         justify-content: flex-end;
//         gap: 6px;
//         margin-top: 4px;
//       }
      
//       .cls3741_msg_status {
//         font-size: 11px;
//         color: var(--text-secondary);
//         opacity: 0.8;
//       }
      
//       .cls3741_msg_status[data-status="read"] {
//         color: #000000;
//         font-weight: 600;
//       }
      
//       .cls3741_msg_status[data-status="failed"] {
//         color: #dc2626;
//       }
      
//       @keyframes spin {
//         0% { transform: rotate(0deg); }
//         100% { transform: rotate(360deg); }
//       }
      
//       .cls3741_media_image, .cls3741_media_video {
//         max-width: 100%;
//         border-radius: 12px;
//         margin-bottom: 8px;
//       }
      
//       .cls3741_contact_badge {
//         transition: all 0.3s ease;
//       }
//     </style>
//   `;
  
//   document.head.insertAdjacentHTML('beforeend', additionalStyles);

// })(); // end IIFE

// }); // DOMContentLoaded








//  (function(){
//       // العناصر الرئيسية
//       const contactsList = document.getElementById('cls3741_contacts_list');
//       const messagesArea = document.getElementById('cls3741_messages_area');
//       const messageInput = document.getElementById('cls3741_message_input');
//       const sendBtn = document.getElementById('cls3741_send_btn');
//       const activeAvatar = document.getElementById('cls3741_active_avatar');
//       const activeName = document.getElementById('cls3741_active_name');
//       const userName = document.getElementById('cls3741_user_name');
//       const userPhone = document.getElementById('cls3741_user_phone');
//       const userAvatar = document.getElementById('cls3741_user_avatar');
//       const openInfo = document.getElementById('cls3741_open_info');
      
//       // عناصر الوسائط
//       const audioBtn = document.getElementById('cls3741_audio_btn');
//       const imageBtn = document.getElementById('cls3741_image_btn');
//       const videoBtn = document.getElementById('cls3741_video_btn');
//       const imageInput = document.getElementById('cls3741_image_input');
//       const videoInput = document.getElementById('cls3741_video_input');
//       const mediaPreview = document.getElementById('cls3741_media_preview');

//       // حالة التسجيل الصوتي
//       let mediaRecorder = null;
//       let audioChunks = [];
//       let isRecording = false;

//       // دالة للتمرير إلى الأسفل
//       function scrollBottom(){
//         messagesArea.scrollTop = messagesArea.scrollHeight;
//       }

//       // إدارة ارتفاع حقل النص تلقائيًا
//       messageInput.addEventListener('input', function() {
//         this.style.height = 'auto';
//         this.style.height = Math.min(this.scrollHeight, 120) + 'px';
//       });

//       // النقر على جهة اتصال
//       contactsList.addEventListener('click', function(e){
//         let target = e.target;
//         while(target && !target.classList.contains('cls3741_contact_item')){
//             target = target.parentElement;
//         }
//         if(target){
//           // تمييز العنصر المحدد
//           contactsList.querySelectorAll('.cls3741_contact_item').forEach(i=>i.style.background='transparent');
//           target.style.background='var(--bg-tertiary)';

//           const name = target.dataset.name;
//           const phone = target.dataset.phone;
//           const initial = name.trim().charAt(0).toUpperCase();

//           // تحديث المعلومات في الرأس
//           activeAvatar.textContent = initial;
//           activeName.textContent = name;
//           userName.textContent = name;
//           userPhone.textContent = '+' + phone.replace(/^(\d+)/,'$1');
//           userAvatar.textContent = initial;

//           // تعيين الهاتف الحالي للنظام
//           if (window.__chatInput) {
//             window.__chatInput.setCurrentPhone(phone);
//           }

//           // تحميل المحادثة (تجريبي)
//           messagesArea.innerHTML = `
//             <div class="cls3741_msg_bubble">مرحبا ${name} — كيف أستطيع مساعدتك؟ <span class="cls3741_msg_time">09:00</span></div>
//             <div class="cls3741_msg_bubble me">مرحبا! أريد تفاصيل الطلب. <span class="cls3741_msg_time">09:03</span></div>
//           `;
//           scrollBottom();
//         }
//       });

//       // إرسال رسالة نصية
//  // دالة إرسال الرسائل المحسنة
// async function sendMessage(fileObj = null, fileType = null) {
//     if (!currentPhone) { 
//         alert('⚠️ يرجى اختيار محادثة أولاً');
//         return; 
//     }

//     // إذا تم استدعاء الدالة بدون معاملات وكان هناك ملف في قائمة الانتظار
//     if (fileObj instanceof Event && !queuedFile) {
//         fileObj = null;
//         fileType = null;
//     }
    
//     const fileToSend = fileObj || queuedFile;
//     const typeToSend = fileType || queuedFileType;

//     // تعطيل زر الإرسال مؤقتاً
//     const sendBtn = document.getElementById('cls3741_send_btn');
//     if (sendBtn) sendBtn.disabled = true;

//     try {
//         if (fileToSend && typeToSend) {
//             // إرسال ملف (صورة، فيديو، صوت)
//             const fd = new FormData();
//             fd.append('file', fileToSend);
//             fd.append('type', typeToSend);
//             fd.append('to', currentPhone);
            
//             const bodyText = inputBody ? inputBody.value.trim() : '';
//             if (bodyText) fd.append('body', bodyText);

//             // عرض معاينة محلية فورية
//             const now = new Date();
//             const hh = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
            
//             let previewMessage = {};
//             if (typeToSend === 'audio') {
//                 previewMessage = {
//                     id: null, 
//                     body: bodyText, 
//                     fromMe: true, 
//                     time: hh, 
//                     type: 'audio', 
//                     url: URL.createObjectURL(fileToSend),
//                     status: 'sending'
//                 };
//             } else if (typeToSend === 'image') {
//                 previewMessage = {
//                     id: null,
//                     body: bodyText,
//                     fromMe: true,
//                     time: hh,
//                     type: 'image',
//                     url: URL.createObjectURL(fileToSend),
//                     status: 'sending'
//                 };
//             } else if (typeToSend === 'video') {
//                 previewMessage = {
//                     id: null,
//                     body: bodyText,
//                     fromMe: true,
//                     time: hh,
//                     type: 'video',
//                     url: URL.createObjectURL(fileToSend),
//                     status: 'sending'
//                 };
//             }
            
//             appendMessages([previewMessage]);

//             // إرسال إلى الخادم
//             const res = await fetch("{% url 'send_message' %}", {
//                 method: 'POST',
//                 headers: { 
//                     'X-CSRFToken': getCsrfToken()
//                 },
//                 body: fd
//             });

//             if (!res.ok) throw new Error(`فشل الإرسال: ${res.status}`);
            
//             const data = await res.json();
//             console.log('✅ تم إرسال الملف بنجاح:', data);

//             // تنظيف قائمة الانتظار والمعاينة
//             queuedFile = null;
//             queuedFileType = null;
//             mediaPreviewArea.innerHTML = '';
            
//             // تحديث المحادثة
//             await fetchMessagesForCurrent();
//             await fetchContactsAndUpdateUI();

//         } else {
//             // إرسال نص عادي
//             const text = inputBody ? inputBody.value.trim() : '';
//             if (!text) {
//                 if (sendBtn) sendBtn.disabled = false;
//                 return;
//             }

//             // عرض معاينة فورية
//             const now = new Date();
//             const hh = `${String(now.getHours()).padStart(2,'0')}:${String(now.getMinutes()).padStart(2,'0')}`;
            
//             appendMessages([{
//                 id: null, 
//                 body: text, 
//                 fromMe: true, 
//                 time: hh, 
//                 type: 'text',
//                 status: 'sending'
//             }]);

//             // مسح حقل الإدخال
//             if (inputBody) inputBody.value = '';

//             // إرسال إلى الخادم
//             const res = await fetch("{% url 'send_message' %}", {
//                 method: 'POST',
//                 headers: { 
//                     'Content-Type': 'application/json', 
//                     'X-CSRFToken': getCsrfToken() 
//                 },
//                 body: JSON.stringify({ 
//                     body: text, 
//                     to: currentPhone, 
//                     media_type: 'text' 
//                 })
//             });

//             if (!res.ok) throw new Error(`فشل الإرسال: ${res.status}`);
            
//             console.log('✅ تم إرسال الرسالة النصية بنجاح');
            
//             // تحديث المحادثة
//             await fetchMessagesForCurrent();
//             await fetchContactsAndUpdateUI();
//         }
//     } catch (err) {
//         console.error('❌ خطأ في إرسال الرسالة:', err);
//         alert('فشل الإرسال: ' + (err.message || err));
        
//         // إظهار رسالة الخطأ في الواجهة
//         const errorMessage = document.createElement('div');
//         errorMessage.className = 'cls3741_error_message';
//         errorMessage.innerHTML = `
//             <div style="background: #fee2e2; color: #dc2626; padding: 8px 12px; border-radius: 8px; margin: 8px 0; font-size: 14px;">
//                 ❌ فشل إرسال الرسالة
//             </div>
//         `;
//         messagesArea.appendChild(errorMessage);
        
//     } finally {
//         // إعادة تمكين زر الإرسال
//         if (sendBtn) sendBtn.disabled = false;
//     }
// }

// // دالة الحصول على توكن CSRF
// function getCsrfToken() {
//     const tokenEl = document.querySelector('[name=csrfmiddlewaretoken]');
//     return tokenEl ? tokenEl.value : '';
// }

// // ربط الأحداث
// document.addEventListener('DOMContentLoaded', function() {
//     const sendBtn = document.getElementById('cls3741_send_btn');
//     const inputBody = document.getElementById('body');
    
//     // زر الإرسال
//     if (sendBtn) {
//         sendBtn.addEventListener('click', (e) => {
//             e.preventDefault();
//             if (queuedFile && queuedFileType) {
//                 sendMessage(queuedFile, queuedFileType);
//             } else {
//                 sendMessage();
//             }
//         });
//     }
    
//     // إرسال بالضغط على Enter
//     if (inputBody) {
//         inputBody.addEventListener('keydown', (e) => {
//             if (e.key === 'Enter' && !e.shiftKey) {
//                 e.preventDefault();
//                 if (queuedFile && queuedFileType) {
//                     sendMessage(queuedFile, queuedFileType);
//                 } else {
//                     sendMessage();
//                 }
//             }
//         });
//     }
// });

     
      
//       // إرسال بالضغط على Enter (بدون Shift)
//       messageInput.addEventListener('keydown', (e)=>{
//         if(e.key === 'Enter' && !e.shiftKey){
//           e.preventDefault();
//           sendMessage();
//         }
//       });

//       // إدارة التسجيل الصوتي
//       audioBtn.addEventListener('click', async function(){
//         try{
//           if(!isRecording){
//             // بدء التسجيل
//             const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
//             mediaRecorder = new MediaRecorder(stream);
//             audioChunks = [];
            
//             mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
//             mediaRecorder.onstop = () => {
//               const blob = new Blob(audioChunks, { type: 'audio/webm' });
//               createMediaPreview(blob, 'audio');
//             };
            
//             mediaRecorder.start();
//             isRecording = true;
//             audioBtn.classList.add('recording');
//           } else {
//             // إيقاف التسجيل
//             mediaRecorder.stop();
//             isRecording = false;
//             audioBtn.classList.remove('recording');
//             // إيقاف التتبع
//             mediaRecorder.stream.getTracks().forEach(track => track.stop());
//           }
//         }catch(e){
//           console.error('خطأ في التسجيل:', e);
//           alert('لا يمكن الوصول إلى الميكروفون. يرجى التحقق من الأذونات.');
//         }
//       });

//       // رفع الصور والفيديوهات
//       imageBtn.addEventListener('click', () => imageInput.click());
//       videoBtn.addEventListener('click', () => videoInput.click());

//       imageInput.addEventListener('change', (e) => {
//         const file = e.target.files[0];
//         if(file) createMediaPreview(file, 'image');
//         imageInput.value = '';
//       });

//       videoInput.addEventListener('change', (e) => {
//         const file = e.target.files[0];
//         if(file) createMediaPreview(file, 'video');
//         videoInput.value = '';
//       });

//       // إنشاء معاينة للوسائط
//       function createMediaPreview(file, type) {
//         const previewItem = document.createElement('div');
//         previewItem.className = `cls3741_preview_item cls3741_preview_${type}`;
        
//         const removeBtn = document.createElement('button');
//         removeBtn.className = 'cls3741_preview_remove';
//         removeBtn.innerHTML = '×';
//         removeBtn.onclick = () => previewItem.remove();
        
//         if(type === 'image') {
//           const img = document.createElement('img');
//           img.className = 'cls3741_preview_image';
//           img.src = URL.createObjectURL(file);
//           previewItem.appendChild(img);
//         } 
//         else if(type === 'video') {
//           const video = document.createElement('video');
//           video.className = 'cls3741_preview_video';
//           video.src = URL.createObjectURL(file);
//           video.controls = true;
//           previewItem.appendChild(video);
//         }
//         else if(type === 'audio') {
//           const audio = document.createElement('audio');
//           audio.controls = true;
//           audio.src = URL.createObjectURL(file);
//           previewItem.className = 'cls3741_preview_item cls3741_preview_audio';
//           previewItem.appendChild(audio);
//         }
        
//         previewItem.appendChild(removeBtn);
//         mediaPreview.appendChild(previewItem);
//       }

//       // فتح/إغلاق معلومات المستخدم
//       openInfo.addEventListener('click', ()=>{
//         const userCol = document.getElementById('cls3741_user_col');
//         userCol.style.display = userCol.style.display === 'none' ? 'flex' : 'none';
//       });

//       // البحث في جهات الاتصال
//       document.getElementById('cls3741_search').addEventListener('input', (e)=>{
//         const q = e.target.value.trim().toLowerCase();
//         contactsList.querySelectorAll('.cls3741_contact_item').forEach(item=>{
//           const name = item.dataset.name.toLowerCase();
//           const phone = item.dataset.phone.toLowerCase();
//           item.style.display = (name.includes(q) || phone.includes(q)) ? 'flex' : 'none';
//         });
//       });

//       // تهيئة: النقر على أول جهة اتصال
//       const first = contactsList.querySelector('.cls3741_contact_item');
//       if(first) first.click();

//       // تعريض الدوال للنظام العام
//       if(!window.__chatInput) window.__chatInput = {};
//       window.__chatInput.setCurrentPhone = function(phone) {
//         window.__currentPhone = phone;
//       };

//     })();
  
  