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
            console.log('💯 new websocket data ' , data )
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
    

    

    switch (type) {
        case "finished":{
            
        const payload = data.payload;
    console.log('💯👀 msg sent succ', payload);

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
        // 🔥 لاحظ الأقواس المربعة [ ] هنا لتحويلها لمصفوفة
        window.appendMessagesws([formattedMsg]); 
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




        case 'new_message_received': {
            const payload = data.payload;
            const incomingPhone = payload.contact.phone;
          


            let messageText = "";

            if (payload.message.type == 'text') {
            messageText = payload.message.body; // نملأ القيمة فقط
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
            // إذا كان الشات مفتوحاً، نكتفي بصوت خفيف جداً (اختياري)
         
            
            
      
            
            
            
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