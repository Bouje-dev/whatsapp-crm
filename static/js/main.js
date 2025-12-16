
const navBtns = document.querySelectorAll('.cls3741_btn');
const panels = document.querySelectorAll('.cls3741_panel');
const sideCards = document.querySelectorAll('.cls3741_sidecard');

navBtns.forEach(btn => {
btn.addEventListener('click', () => {
const target = btn.getAttribute('data-target');

// إزالة الاكتف من الأزرار
navBtns.forEach(b => b.classList.remove('cls3741_btn_active'));
btn.classList.add('cls3741_btn_active');

// إخفاء كل البطاقات
panels.forEach(p => p.style.display = 'none');
sideCards.forEach(s => s.classList.remove('cls3741_sidecard_visible'));

// إظهار البطاقة المناسبة
const panel = document.querySelector(`.cls3741_panel_${target}`);
if (panel) panel.style.display = 'block';

const side = document.querySelector(`.cls3741_sidecard_${target}`);
if (side) side.classList.add('cls3741_sidecard_visible');
});
});

// اغلاق البطاقة الجانبية
document.querySelectorAll('.cls3741_close_side').forEach(btn => {
btn.addEventListener('click', (e) => {
e.target.closest('.cls3741_sidecard').classList.remove('cls3741_sidecard_visible');
});
});













(function(){
    // --- المتغيرات العامة ---
    let currentMode = 'text';
    let currentObjectURL = null;
    let buttons = []; 
    const MAX_BUTTONS = 3;
    let bodySamples = {}; 

    // قراءة الإعدادات من HTML
    const CONFIG = window.TEMPLATE_CONFIG || {};
    const API_URLS = CONFIG.urls || {};

    // --- عناصر الواجهة ---
    const inputArea = document.getElementById('input_area');
    const waHeader = document.getElementById('wa_header');
    const waBody = document.getElementById('wa_body');
    const waFooter = document.getElementById('wa_footer_area');
    const bodyText = document.getElementById('body_text');
    const bodyCount = document.getElementById('body_count');
    const footerEl = document.getElementById('template_footer');
    const buttonsListWrap = document.getElementById('buttons_list');
    const waButtons = document.getElementById('wa_buttons');
    const tbody = document.getElementById('templates_tbody');
    
    // عناصر التحكم في النموذج
    const createSection = document.getElementById('template_create_section');
    const tableWrap = document.getElementById('templates_table_wrap');
    const errorBox = document.getElementById('formErrors');
    const saveBtn = document.getElementById('template_save_btn');
    const refreshBtn = document.getElementById('templates_refresh_btn');
    const cancelBtn = document.getElementById('template_cancel_btn');
    const createBtn = document.getElementById('templates_create_btn');

    // أزرار الوسائط
    const btnText = document.getElementById('btn_text');
    const btnImage = document.getElementById('btn_image');
    const btnVideo = document.getElementById('btn_video');
    const btnDoc = document.getElementById('btn_doc');
    
    // حقول الملفات
    const fileImage = document.getElementById('file_image');
    const fileVideo = document.getElementById('file_video');
    const fileDoc = document.getElementById('file_doc');

    // عناصر الأزرار
    const addButtonBtn = document.getElementById('btn_add_button');
    const newButtonType = document.getElementById('new_button_type');
  function getCsrfToken(){
    const tokenEl = document.querySelector('[name=csrfmiddlewaretoken]');
    return tokenEl ? tokenEl.value : '';
  }

    // عنصر المتغيرات
    let bodyVarsWrap = document.getElementById('body_vars');
    if (!bodyVarsWrap && bodyText) {
        bodyVarsWrap = document.createElement('div');
        bodyVarsWrap.id = 'body_vars';
        bodyVarsWrap.style.marginTop = '10px';
        bodyText.parentNode.insertBefore(bodyVarsWrap, bodyText.nextSibling);
    }

    const editingInput = document.getElementById('editing_template_id');
    const existingHeaderPreview = document.getElementById('existing_header_preview');


    // --- دوال مساعدة ---
    // function getCsrfToken() {
    //     return CONFIG.csrfToken || '';
    // }

    function escapeHtml(s) {
        return (s||'').toString().replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;').replace(/'/g,'&#039;');
    }

    function nl2br(s) {
        return escapeHtml(s || '').replace(/\r?\n/g, '<br>');
    }

    function isValidUrl(u) {
        try { new URL(u); return true; } catch(e){ return false; }
    }

    // --- 1. تحميل القوالب ---
    window.loadTemplates = async function(specificChannelId = null) {
        if (!tbody) return;

        const activeId = specificChannelId || window.currentChannelId || CONFIG.initialChannelId;
        
        if (!activeId || activeId === 'null') {
            tbody.innerHTML = `<tr><td colspan="6" style="padding:40px;text-align:center;">لا توجد قناة محددة</td></tr>`;
            return;
        }

        tbody.innerHTML = `<tr><td colspan="6" style="padding:40px;text-align:center;color:var(--text-muted);">جاري تحميل القوالب...</td></tr>`;

        try {
            // استخدام الرابط من Config
            const url = `${API_URLS.apiTemplates}?channel_id=${activeId}`;
            
            const response = await fetch(url, {
                headers: { 'Accept': 'application/json', 'X-CSRFToken': getCsrfToken() }
            });

            if (response.ok) {
                const data = await response.json();
                renderTemplates(data.templates || []);
            } else {
                const err = await response.json();
                throw new Error(err.error || 'فشل التحميل');
            }
        } catch (error) {
            console.error('Template Load Error:', error);
            tbody.innerHTML = `<tr><td colspan="6" style="padding:40px;text-align:center;color:var(--danger);">فشل التحميل: ${error.message}</td></tr>`;
        }
    };

    function renderTemplates(templates) {
        if (!templates || templates.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" style="padding:40px;text-align:center;color:var(--text-muted);">لا توجد قوالب بعد</td></tr>`;
            return;
        }

        tbody.innerHTML = templates.map(template => `
            <tr style="border-bottom:1px solid var(--border-color);">
                <td style="padding:12px;color:var(--text-primary);">${escapeHtml(template.name)}</td>
                <td style="padding:12px;color:var(--text-secondary);">
                    <span style="background:var(--bg-hover);padding:4px 8px;border-radius:4px;font-size:12px;">
                        ${escapeHtml(template.category)}
                    </span>
                </td>
                <td style="padding:12px;color:var(--text-secondary);max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                    ${escapeHtml(template.body ? template.body.substring(0, 30) + '...' : '-')}
                </td>
                <td style="padding:12px;text-align:center;">
                    <span style="background:${template.status === 'APPROVED' ? 'var(--success)' : 'var(--warning)'};color:white;padding:4px 12px;border-radius:12px;font-size:11px;font-weight:bold;">
                        ${template.status}
                    </span>
                </td>
                <td style="padding:12px;color:var(--text-secondary);font-size:13px;">
                    ${template.created_at ? new Date(template.created_at).toLocaleDateString('en-GB') : '-'}
                </td>
                <td style="padding:12px;text-align:center;">
                    <button class="cls3741_btn update-template-btn" onclick="window.editTemplate('${template.id}')" style="padding:6px 12px;border:1px solid var(--border-color);border-radius:6px;background:transparent;color:var(--text-primary);cursor:pointer;">
                        تعديل
                    </button>
                </td>
            </tr>
        `).join('');
    }

    // --- 2. إدارة النموذج (Form Handling) ---
    
    function setActiveTab(btn) {
        [btnText, btnImage, btnVideo, btnDoc].forEach(b => {
            if (b) b.classList.toggle('active', b === btn);
        });
    }

    function clearInputArea() {
        if (inputArea) inputArea.innerHTML = '';
    }

    function revokeObjectURL() {
        if (currentObjectURL) {
            URL.revokeObjectURL(currentObjectURL);
            currentObjectURL = null;
        }
    }

    function showTextInput() {
        if (!inputArea) return;
        clearInputArea();
        const textarea = document.createElement('textarea');
        textarea.className = 'form-textarea';
        textarea.rows = 4;
        textarea.placeholder = 'اكتب نص العنوان هنا...';
        textarea.addEventListener('input', function() {
            updateHeaderPreview();
        });
        inputArea.appendChild(textarea);
        updateHeaderPreview();
    }

    function showFileUpload(type) {
        if (!inputArea) return;
        clearInputArea();
        const uploader = document.createElement('div');
        uploader.className = 'file-uploader';
        
        const label = document.createElement('div');
        label.className = 'small-muted';
        label.textContent = type === 'image' ? 'اختر صورة' : (type === 'video' ? 'اختر فيديو' : 'اختر ملف');
        
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'upload-btn';
        button.textContent = 'رفع ملف';
        
        button.addEventListener('click', () => {
            if (type === 'image' && fileImage) fileImage.click();
            else if (type === 'video' && fileVideo) fileVideo.click();
            else if (type === 'doc' && fileDoc) fileDoc.click();
        });
        
        uploader.appendChild(label);
        uploader.appendChild(button);
        inputArea.appendChild(uploader);

        const fileInput = type === 'image' ? fileImage : type === 'video' ? fileVideo : fileDoc;
        if (fileInput) {
            fileInput.onchange = function() {
                label.textContent = this.files[0] ? this.files[0].name : 'لم يتم اختيار ملف';
                updateHeaderPreview();
            };
        }
    }

    function updateHeaderPreview() {
        revokeObjectURL();
        if (!waHeader) return;

        if (currentMode === 'text') {
            const textarea = inputArea ? inputArea.querySelector('textarea') : null;
            waHeader.innerHTML = textarea ? nl2br(textarea.value) : '';
        } else if (currentMode === 'image') {
            const file = fileImage ? fileImage.files[0] : null;
            if (file) {
                const url = URL.createObjectURL(file);
                currentObjectURL = url;
                waHeader.innerHTML = `<img src="${url}" style="max-width:100%;border-radius:8px;">`;
            } else waHeader.innerHTML = '';
        } else {
            waHeader.innerHTML = `<div class="small-muted">ملف مرفق</div>`;
        }
    }

    function updateBodyPreview() {
        const value = bodyText ? bodyText.value : '';
        let previewText = value;
        
        // استبدال المتغيرات
        for (let i = 1; i <= 20; i++) {
            const val = bodySamples[String(i)] || `{{${i}}}`;
            previewText = previewText.replace(new RegExp(`\\[\\[${i}\\]\\]`, 'g'), val);
            // دعم الصيغة القديمة أيضاً
            previewText = previewText.replace(new RegExp(`\\{\\{${i}\\}\\}`, 'g'), val);
        }

        if (waBody) waBody.innerHTML = previewText ? nl2br(escapeHtml(previewText)) : '<span style="color:#999;">المعاينة</span>';
        if (bodyCount) bodyCount.textContent = value.length;
        
        syncVariablesWithBody();
    }

    function syncVariablesWithBody() {
        const text = bodyText ? bodyText.value : '';
        // البحث عن {{1}} أو [[1]]
        const re = /\[\[\s*(\d+)\s*\]\]|\{\{\s*(\d+)\s*\}\}/g;
        const nums = new Set();
        let m;
        while ((m = re.exec(text)) !== null) {
            nums.add(parseInt(m[1] || m[2], 10));
        }
        const found = Array.from(nums).sort((a,b)=>a-b);

        if (found.length === 0) {
            bodyVarsWrap.innerHTML = `<button type="button" id="insert_var_btn" class="upload-btn">إدراج متغير {{1}}</button>`;
            document.getElementById('insert_var_btn')?.addEventListener('click', () => insertAtCursor(bodyText, '{{1}}'));
            return;
        }

        let html = '<div style="display:flex;flex-direction:column;gap:8px;">';
        found.forEach(i => {
            const val = bodySamples[String(i)] || '';
            html += `
                <div style="display:flex;gap:8px;align-items:center;">
                    <label style="min-width:40px;">{{${i}}}</label>
                    <input type="text" data-idx="${i}" class="body-sample-input" value="${escapeHtml(val)}" placeholder="مثال للمتغير ${i}" style="flex:1;padding:6px;border-radius:4px;border:1px solid var(--border-color);background:var(--bg-primary);color:var(--text-primary);">
                </div>`;
        });
        html += `<button type="button" id="add_next_var" class="upload-btn" style="margin-top:5px;">متغير جديد {{${Math.max(...found)+1}}}</button></div>`;
        
        bodyVarsWrap.innerHTML = html;

        bodyVarsWrap.querySelectorAll('.body-sample-input').forEach(inp => {
            inp.addEventListener('input', (e) => {
                bodySamples[e.target.dataset.idx] = e.target.value;
                updateBodyPreview(); // تحديث المعاينة فقط
            });
        });

        document.getElementById('add_next_var')?.addEventListener('click', () => {
            const next = Math.max(...found) + 1;
            insertAtCursor(bodyText, `{{${next}}}`);
        });
    }

    function insertAtCursor(el, text) {
        if (!el) return;
        const start = el.selectionStart || 0;
        const end = el.selectionEnd || 0;
        el.value = el.value.slice(0, start) + text + el.value.slice(end);
        updateBodyPreview();
        el.focus();
    }

    // ----- إدارة الأزرار -----
    function createButtonObject(type) {
        return { type, text: '', url: '', phone: '' };
    }

    function renderButtonsList() {
        if (!buttonsListWrap) return;
        buttonsListWrap.innerHTML = '';
        
        buttons.forEach((btn, idx) => {
            const item = document.createElement('div');
            item.className = 'buttons-list-item';
            item.innerHTML = `
                <span style="font-size:12px;padding:2px 6px;background:#eee;border-radius:4px;color:#333;">${btn.type}</span>
                <input type="text" placeholder="نص الزر" class="btn-text-input" value="${escapeHtml(btn.text)}" style="flex:1;padding:6px;border-radius:4px;border:1px solid #ddd;">
                ${btn.type === 'URL' ? `<input type="url" placeholder="https://" class="btn-url-input" value="${escapeHtml(btn.url)}" style="flex:1;padding:6px;">` : ''}
                ${btn.type === 'PHONE_NUMBER' ? `<input type="tel" placeholder="+966..." class="btn-phone-input" value="${escapeHtml(btn.phone)}" style="flex:1;padding:6px;">` : ''}
                <button class="btn-remove" style="color:red;border:none;background:none;cursor:pointer;">✕</button>
            `;
            
            item.querySelector('.btn-text-input').addEventListener('input', (e) => { buttons[idx].text = e.target.value; renderButtonsPreview(); });
            if(item.querySelector('.btn-url-input')) item.querySelector('.btn-url-input').addEventListener('input', (e) => buttons[idx].url = e.target.value);
            if(item.querySelector('.btn-phone-input')) item.querySelector('.btn-phone-input').addEventListener('input', (e) => buttons[idx].phone = e.target.value);
            item.querySelector('.btn-remove').addEventListener('click', () => { buttons.splice(idx, 1); renderButtonsList(); renderButtonsPreview(); });
            
            buttonsListWrap.appendChild(item);
        });
        renderButtonsPreview();
    }

    function renderButtonsPreview() {
        if (!waButtons) return;
        waButtons.innerHTML = '';
        buttons.forEach(btn => {
            const b = document.createElement('div');
            b.className = 'wa-btn';
            b.textContent = btn.text || 'زر بلا نص';
            b.style.cssText = "background:white;color:#00a884;text-align:center;padding:10px;margin-top:5px;border-radius:6px;font-weight:bold;box-shadow:0 1px 1px rgba(0,0,0,0.1);cursor:pointer;";
            waButtons.appendChild(b);
        });
    }

    // --- 3. إرسال البيانات (Submit) ---
    async function submitTemplate(e) {
        if(e) e.preventDefault();
        
        if(saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'جاري الحفظ...'; }
        if(errorBox) { errorBox.style.display = 'none'; }

        const name = document.getElementById('template_name')?.value;
        const body = bodyText?.value;

        if (!name || !body) {
            alert('يرجى إدخال الاسم ونص الرسالة');
            if(saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'حفظ'; }
            return;
        }

        const formData = new FormData();
        formData.append('name', name);
        formData.append('category', document.getElementById('template_category_select')?.value || 'UTILITY');
        formData.append('language', document.getElementById('template_language')?.value || 'ar');
        formData.append('body', body);
        formData.append('footer', footerEl?.value || '');
        formData.append('header_type', currentMode);
        formData.append('channel_id', window.currentChannelId);

        // ملفات الهيدر
        if (currentMode === 'text') {
            const ta = inputArea.querySelector('textarea');
            if(ta) formData.append('header_text', ta.value);
        } else if (currentMode === 'image' && fileImage?.files[0]) {
            formData.append('header_image', fileImage.files[0]);
        } else if (currentMode === 'video' && fileVideo?.files[0]) {
            formData.append('header_video', fileVideo.files[0]);
        } else if (currentMode === 'doc' && fileDoc?.files[0]) {
            formData.append('header_document', fileDoc.files[0]);
        }

        // الأزرار والمتغيرات
        formData.append('buttons', JSON.stringify(buttons));
        
        // تحويل samples object إلى مصفوفة مرتبة
        const samplesArray = [];
        Object.keys(bodySamples).sort((a,b)=>a-b).forEach(k => {
            if(bodySamples[k]) samplesArray.push({type:'text', text: bodySamples[k]});
        });
        formData.append('body_samples', JSON.stringify(samplesArray));

        const editingId = editingInput?.value;
        const url = editingId 
            ? `/discount/whatssapAPI/api/templates/${editingId}/` 
            : API_URLS.createTemplate;

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() },
                body: formData
            });

            if (response.ok) {
                alert('تم الحفظ بنجاح!');
                if(createSection) createSection.style.display = 'none';
                if(tableWrap) tableWrap.style.display = 'block';
                window.loadTemplates();
            } else {
                const err = await response.json();
                throw new Error(err.error || 'فشل الحفظ');
            }
        } catch (error) {
            alert('خطأ: ' + error.message);
        } finally {
            if(saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'حفظ'; }
        }
    }

    // --- 4. التعديل (Edit) ---
    window.editTemplate = async function(templateId) {
        if(createSection) createSection.style.display = 'block';
        if(tableWrap) tableWrap.style.display = 'none';
        if(editingInput) editingInput.value = templateId;
        
        try {
            // استخدام الرابط من Config
            const url = `${CONFIG.urls.templateShow}${templateId}/`;
            const res = await fetch(url, { headers: {'Accept': 'application/json'} });
            const data = await res.json();
            
            if(data.template) {
                const t = data.template;
                document.getElementById('template_name').value = t.name;
                bodyText.value = t.body;
                
                // استعادة الأزرار
                buttons = [];
                if(t.buttons && Array.isArray(t.buttons)) {
                    buttons = t.buttons.map(b => ({
                        type: b.type, text: b.text, url: b.url||'', phone: b.phone_number||''
                    }));
                }
                renderButtonsList();
                updateBodyPreview();
            }
        } catch(e) {
            console.error(e);
            alert("فشل تحميل بيانات القالب");
        }
    };

    function resetForm() {
        if(editingInput) editingInput.value = '';
        document.getElementById('template_name').value = '';
        bodyText.value = '';
        buttons = [];
        renderButtonsList();
        updateBodyPreview();
    }

    // --- تهيئة الصفحة ---
    document.addEventListener('DOMContentLoaded', function() {
        // الأحداث
        if (btnText) btnText.addEventListener('click', () => { setActiveTab(btnText); currentMode = 'text'; showTextInput(); });
        if (btnImage) btnImage.addEventListener('click', () => { setActiveTab(btnImage); currentMode = 'image'; showFileUpload('image'); });
        if (btnVideo) btnVideo.addEventListener('click', () => { setActiveTab(btnVideo); currentMode = 'video'; showFileUpload('video'); });
        if (btnDoc) btnDoc.addEventListener('click', () => { setActiveTab(btnDoc); currentMode = 'doc'; showFileUpload('doc'); });
        
        if (bodyText) bodyText.addEventListener('input', updateBodyPreview);
        if (footerEl) footerEl.addEventListener('input', () => { if(waFooter) waFooter.textContent = footerEl.value; });

        if (addButtonBtn) addButtonBtn.addEventListener('click', () => {
            if (buttons.length >= MAX_BUTTONS) return alert('الحد الأقصى 3 أزرار');
            const type = newButtonType ? newButtonType.value : 'QUICK_REPLY';
            buttons.push(createButtonObject(type));
            renderButtonsList();
        });

        if (createBtn) createBtn.addEventListener('click', () => {
            createSection.style.display = 'block';
            tableWrap.style.display = 'none';
            resetForm();
            showTextInput()
        });

        if (cancelBtn) cancelBtn.addEventListener('click', () => {
            createSection.style.display = 'none';
            tableWrap.style.display = 'block';
        });

        if (saveBtn) saveBtn.addEventListener('click', submitTemplate);

        if (refreshBtn) refreshBtn.addEventListener('click', async () => {
            refreshBtn.disabled = true;
            refreshBtn.textContent = 'Syncing...';
            try {
                await fetch(`${API_URLS.syncTemplates}?channel_id=${window.currentChannelId}`);
                window.loadTemplates();
                alert('تم التحديث');
            } catch(e) { alert('فشل التحديث'); }
            finally { refreshBtn.disabled = false; refreshBtn.textContent = 'Sync'; }
        });

        // التحميل الأولي
        if (window.currentChannelId) {
            window.loadTemplates(window.currentChannelId);
        }
    });

})();





















/**
 * showSendError(resData, options)
 *   - resData: JSON response from backend { error: "...", reason: "..." }
 *   - options: optional { wrapperSelector, onRetry, onSelectTemplate, autoDismissMs }
 *
 * Usage:
 *   await resData = await res.json();
 *   showSendError(resData, {
 *     onRetry: () => sendMessageLocal(...),           // توصيل إعادة المحاولة لديك
 *     onSelectTemplate: () => openTemplatePanel(),   // فتح واجهة اختيار القالب
 *   });
 */
function showSendErrorchat(resData = {}, options = {}) {
  const {
    wrapperSelector = '.cls3741_chat_input_wrapper',
    onRetry = null,
    onSelectTemplate = null,
    autoDismissMs = 8000
  } = options;

  const wrapper = document.querySelector(wrapperSelector);
  if (!wrapper) return console.log('showSendError: wrapper not found:', wrapperSelector);
    

  // نصوص آمنة
  const title = (resData.error && String(resData.error).trim()) || 'حدث خطأ أثناء الإرسال';
  const reason = (resData.reason && String(resData.reason).trim()) || (resData.details && String(resData.details).trim()) || '';

  // احذف أي بانر قديم
  const existing = wrapper.querySelector('.error-banner');
  if (existing) existing.remove();

  // بناء العنصر

  const el = document.createElement('div');
  el.className = 'error-banner';
  el.setAttribute('role', 'alert');
  el.innerHTML = `
    <div class="icon" aria-hidden="true">⚠️</div>
    <div class="texts">
      <div class="title">${escapeHtml(title)}</div>
      <div class="reason">${escapeHtml(reason)}</div>
      <div class="actions">
        <button class="action-btn retry-btn" type="button"> Try again</button>
        <span class="tpl-wrap">
          <button class="action-btn secondary select-tpl-btn select-tpl" type="button"> Select Templaite</button>
          
        </span>
      </div>
    </div>
    <button class="close-btn" aria-label="إغلاق">✕</button>
  `;

  // إدراج في DOM (نضعه أعلى المحتوى داخل wrapper)
  wrapper.prepend(el);
document.querySelector('.cls3741_input_container').classList.add('d-none')
  // أحداث الأزرار
  const retryBtn = el.querySelector('.retry-btn');
  const tplBtn = el.querySelector('.select-tpl-btn');
  const closeBtn = el.querySelector('.close-btn');

  let dismissTimer = null;
  const startAutoDismiss = () => {
    if (!autoDismissMs) return;
    clearTimeout(dismissTimer);
    dismissTimer = setTimeout(() => fadeOutAndRemove(el), autoDismissMs);
  };
  const stopAutoDismiss = () => clearTimeout(dismissTimer);

//   el.addEventListener('mouseenter', stopAutoDismiss);
//   el.addEventListener('mouseleave', startAutoDismiss);

//   startAutoDismiss();

  // Retry callback (اترك الفعل لك لربطه بدالتك)
  retryBtn.addEventListener('click', (ev) => {
    ev.preventDefault();
    fadeOutAndRemove(el);
    if (typeof onRetry === 'function') {
      try { onRetry(); } catch (e) { console.error('onRetry failed', e); }
    } else {
      // إذا لم توفّر onRetry، نطلق حدثًا يمكن التقاطه من قِبل كود آخر
      wrapper.dispatchEvent(new CustomEvent('chat9999:retry-send', { detail: { resData } }));
    }
  });

  // Select template callback
  tplBtn.addEventListener('click', (ev) => {
    ev.preventDefault();
    if (typeof onSelectTemplate === 'function') {
      try { onSelectTemplate(); } catch (e) { console.error('onSelectTemplate failed', e); }
    } else {
      wrapper.dispatchEvent(new CustomEvent('chat9999:open-template', { detail: { resData } }));
    }
  });

 

  // Close button
  closeBtn.addEventListener('click', () => fadeOutAndRemove(el));

  // helper functions
  function fadeOutAndRemove(node) {
    node.style.transition = 'opacity 220ms ease, transform 220ms ease';
    node.style.opacity = '0';
    node.style.transform = 'translateY(6px)';
    setTimeout(() => { if (node && node.parentNode) node.parentNode.removeChild(node); }, 240);
  }

  // escaping (safety)
  function escapeHtml(str) {
    return String(str || '').replace(/[&<>"'`=\/]/g, function(s){
      return ({
        '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;','/':'&#x2F;','`':'&#x60;','=':'&#x3D;'
      })[s];
    });
  }
}


// داخل السكريبت القديم أو عند استدعاء الخطأ


     
 
  