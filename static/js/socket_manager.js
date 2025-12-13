const ChatSocket = {
    socket: null,
    
    // 1. دالة تهيئة الاتصال (تستدعى مرة واحدة عند تحميل الموقع)
    init: function(object) {
        const wsprotocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const url = wsprotocol + '://' + window.location.host + '/chat/stream/'; 
        this.socket = new WebSocket(url);

        // ربط الأحداث
        this.socket.onopen = () => console.log("✅ Socket Connected!");
        this.socket.onclose = () => {
            
            setTimeout(() => ChatSocket.init(), 2000); // ✅ صحيح
                
        }
        
        // هنا "الموزع" الذي يستقبل الرسائل
        this.socket.onmessage = (e) => {
            const data = JSON.parse(e.data);
            this.handleIncomingMessage(data);
            console.log('data received' , data)
            
        };
    },




    // 2. دالة الإرسال العامة (Global Sender)
    // أي دالة أخرى في مشروعك ستستخدم هذه الدالة للإرسال
    send: function(type, payload) {
        console.log('data to send '  , payload)
        if (this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify({
                'type': type,       // مثلاً: 'new_message'
                'payload': payload  // البيانات الفعلية
            }));
        } else {
            console.error("Socket is not open.");
        }
    },



    
 handleIncomingMessage: function(data) {
    const type = data.data_type;  
    
    console.log('type' , type)

    switch (type) {


        case 'log_message_received': {
            const payload = data.payload;
            
           console.log('🔥 New system log message:' ,[payload.message]);
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
            console.log('🪪🪪 New message received:' ,[payload]);
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

        case 'message_status_update':{
            const payload = data.payload;
            console.log('Message ststus' , payload)
            const msgStatusIcon = document.querySelector(`[data-msg-id="${data.payload.message_id}"] .cls3741_msg_status`);
            
            if (msgStatusIcon) {
        const newIconSVG = window.getStatusIconHTML(data.payload.status);
        msgStatusIcon.innerHTML = newIconSVG;
            }
       
            break;
 }




        case  'existing_customer_message':{
            const payload = data.payload;
             if (typeof window.updateContactItemSingle === 'function') {
                window.updateContactItemSingle(payload.message);
            }
            break;


}

        case 'update_sidebar_contact': {
    const contactData = data.payload;
    console.log('🔄 Sidebar update signal:', contactData);

    // هنا نستدعي دالة التحديث مباشرة
    if (typeof window.updateContactItemSingle === 'function') {
        
        // 💡 تحسين إضافي: نحاول الحفاظ على الاسم والصورة القديمة إذا كانت موجودة
        // لأن الباك إند قد يرسل الرقم فقط كاسم
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

        // تنفيذ التحديث
        window.updateContactItemSingle(contactData);
    }
    break;
}


        case 'new_message_received': {
            const payload = data.payload;
            const incomingPhone = payload.contact.phone;
            console.log('📥 New message received:', payload);
            if (!payload.message) return;


            let messageText = "";

            if (payload.message.type == 'text') {
            messageText = payload.message.body;  
            } else {
                if(payload.message.type == 'image'){
                    messageText = "Image";
                }  
                if( payload.message.type == 'video'){
                    messageText = "Video";
                }   
                if( payload.message.type == 'audio'){
                    messageText = "Audio";
                }
            }




  
            if (typeof window.highlightOrderRow === 'function'){
                window.highlightOrderRow(payload.contact.phone);
                   }

            if (typeof window.updateContactItemSingle === 'function') {
            
                window.updateContactItemSingle(payload.contact , payload.message);
            }
            const activePhone = (typeof window.getCurrentChatPhone === 'function') 
                                ? window.getCurrentChatPhone() 
                                : null;
            if (activePhone && (activePhone == payload.contact.phone)) { 
                if (typeof window.appendMessagesws === 'function') {
                    window.appendMessagesws([payload.message]); 
                }
            }
            if (activePhone && (activePhone != payload.contact.phone )){

                }


            
            if ( typeof window.updateinterface === 'function') window.updateinterface(window.updateinterface(payload))
            
            
            const cleanIncoming = incomingPhone.replace(/\D/g, '');
            const cleanActive = activePhone ? activePhone.replace(/\D/g, '') : '';

            if (cleanIncoming !== cleanActive) {
        
                // استدعاء دالة الإشعار التي بنيناها
                if (typeof window.showNotification === 'function') {
                    window.showNotification(
                        `${payload.contact.name || incomingPhone}`, // العنوان
                        messageText, // النص
                        
                        // عند النقر على الإشعار: نفتح الشات
                        function() {
                            if (window.__chatSelectPhone) {
                                window.__chatSelectPhone(incomingPhone, payload.contact.name);
                            }
                        }
                    );
                }
            } 
             
         
            
            
      
            
            
            
            else {
                console.log(`🔔 Notification: New msg from ${payload.contact.phone}, but you are on ${activePhone}`);
                // هنا يمكنك تشغيل صوت تنبيه بسيط
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