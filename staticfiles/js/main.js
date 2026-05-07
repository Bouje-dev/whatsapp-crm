
const navBtns = document.querySelectorAll('.cls3741_btn[data-target]');
const panels = document.querySelectorAll('.cls3741_panel');
const sideCards = document.querySelectorAll('.cls3741_sidecard');

function maybeLazyLoadPanelScripts(target) {
  if (target === 'dashboard' && typeof window.ensureDashboardData === 'function') {
    if (!window.__dashboardDataLoaded) {
      window.__dashboardDataLoaded = true;
      window.ensureDashboardData();
    }
  }
}

navBtns.forEach(btn => {
btn.addEventListener('click', () => {
const target = btn.getAttribute('data-target');
if (!target) return;

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

maybeLazyLoadPanelScripts(target);
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
                credentials: 'same-origin',
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
            tbody.innerHTML = `<tr><td colspan="6" style="padding:40px;text-align:center;color:var(--text-muted);"> There are no templates</td></tr>`;
            return;
        }

        function statusPill(st) {
            const s = (st || '').toUpperCase();
            let cls = 'wa-tpl-pill--wait';
            if (s === 'APPROVED') cls = 'wa-tpl-pill--ok';
            else if (s === 'REJECTED' || s === 'DELETED' || s === 'DISABLED') cls = 'wa-tpl-pill--bad';
            return `<span class="wa-tpl-pill ${cls}">${escapeHtml(st || '—')}</span>`;
        }

        tbody.innerHTML = templates.map(template => `
            <tr>
                <td style="font-weight:600;color:#f8fafc;">${escapeHtml(template.name)}</td>
                <td>
                    <span style="background:rgba(99,102,241,0.15);padding:4px 10px;border-radius:8px;font-size:12px;color:#c4b5fd;">
                        ${escapeHtml(template.category || '—')}
                    </span>
                </td>
                <td style="max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#94a3b8;">
                    ${escapeHtml(template.body ? template.body.substring(0, 42) + (template.body.length > 42 ? '…' : '') : '—')}
                </td>
                <td style="text-align:center;">
                    ${statusPill(template.status)}
                </td>
                <td style="color:#94a3b8;font-size:13px;">
                    ${template.created_at ? new Date(template.created_at).toLocaleDateString('en-GB') : '—'}
                </td>
                <td style="text-align:center;">
                    <button type="button" class="cls3741_btn update-template-btn" onclick="window.editTemplate('${template.id}')" style="padding:6px 14px;border:1px solid rgba(148,163,184,0.25);border-radius:999px;background:rgba(15,23,42,0.6);color:#e2e8f0;cursor:pointer;font-size:12px;font-weight:600;">
                     Edit
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

    function updateHeaderHintVisibility(isText) {
        var ht = document.getElementById('header_type_hint_text');
        var hm = document.getElementById('header_type_hint_media');
        if (ht) ht.style.display = isText ? '' : 'none';
        if (hm) hm.style.display = isText ? 'none' : '';
    }

    function setMediaHeaderHint(type) {
        var hm = document.getElementById('header_type_hint_media');
        if (!hm) return;
        var lines = {
            image: 'JPEG, PNG, WebP or GIF · max 5 MB. Remove anytime before submit.',
            video: 'MP4, MOV or WebM · max 5 MB. Remove anytime before submit.',
            doc: 'PDF or Word · max 5 MB. Remove anytime before submit.'
        };
        hm.textContent = lines[type] || '';
    }

    function showTextInput() {
        if (!inputArea) return;
        clearInputArea();
        updateHeaderHintVisibility(true);
        const textarea = document.createElement('textarea');
        textarea.className = 'form-textarea';
        textarea.rows = 3;
        textarea.maxLength = 60;
        textarea.placeholder = 'Short header (max 60 characters for WhatsApp)';
        textarea.addEventListener('input', function() {
            const cc = document.getElementById('chars_count');
            if (cc) cc.textContent = String(textarea.value.length);
            updateHeaderPreview();
        });
        inputArea.appendChild(textarea);
        const cc = document.getElementById('chars_count');
        if (cc) cc.textContent = '0';
        updateHeaderPreview();
    }

    function showFileUpload(type) {
        if (!inputArea) return;
        clearInputArea();
        updateHeaderHintVisibility(false);
        setMediaHeaderHint(type);

        var fileInput = type === 'image' ? fileImage : type === 'video' ? fileVideo : fileDoc;
        if (!fileInput) return;

        var zone = document.createElement('div');
        zone.className = 'wa-tpl-media-zone';

        var drop = document.createElement('div');
        drop.className = 'wa-tpl-media-drop';
        var icon = type === 'image' ? 'fa-image' : (type === 'video' ? 'fa-film' : 'fa-file-alt');
        drop.innerHTML = '<div class="wa-tpl-media-drop-inner">' +
            '<span class="wa-tpl-media-drop-icon"><i class="fas ' + icon + '"></i></span>' +
            '<p class="wa-tpl-media-drop-title">Drag & drop or choose a file</p>' +
            '<p class="wa-tpl-media-drop-sub">This file is sent to Meta as the header sample for review.</p>' +
            '<button type="button" class="wa-tpl-btn-choose-media"><i class="fas fa-folder-open"></i> Choose file</button>' +
            '</div>';

        var fileRow = document.createElement('div');
        fileRow.className = 'wa-tpl-media-file-row';
        fileRow.style.display = 'none';
        var thumbWrap = document.createElement('div');
        thumbWrap.className = 'wa-tpl-media-thumb';
        var metaCol = document.createElement('div');
        metaCol.className = 'wa-tpl-media-meta';
        var nameEl = document.createElement('div');
        nameEl.className = 'wa-tpl-media-name';
        var sizeEl = document.createElement('div');
        sizeEl.className = 'wa-tpl-media-size';
        var actions = document.createElement('div');
        actions.className = 'wa-tpl-media-actions';
        var btnReplace = document.createElement('button');
        btnReplace.type = 'button';
        btnReplace.className = 'wa-tpl-btn-replace-media';
        btnReplace.innerHTML = '<i class="fas fa-sync-alt"></i> Replace';
        var btnRemove = document.createElement('button');
        btnRemove.type = 'button';
        btnRemove.className = 'wa-tpl-btn-remove-media';
        btnRemove.innerHTML = '<i class="fas fa-trash-alt"></i> Remove';
        actions.appendChild(btnReplace);
        actions.appendChild(btnRemove);
        metaCol.appendChild(nameEl);
        metaCol.appendChild(sizeEl);
        metaCol.appendChild(actions);
        fileRow.appendChild(thumbWrap);
        fileRow.appendChild(metaCol);

        zone.appendChild(drop);
        zone.appendChild(fileRow);
        inputArea.appendChild(zone);

        function humanSize(n) {
            if (n < 1024) return n + ' B';
            if (n < 1048576) return (n / 1024).toFixed(1) + ' KB';
            return (n / 1048576).toFixed(1) + ' MB';
        }

        function renderThumb(f) {
            if (thumbWrap._videoUrl) {
                try { URL.revokeObjectURL(thumbWrap._videoUrl); } catch (e) {}
                thumbWrap._videoUrl = null;
            }
            thumbWrap.innerHTML = '';
            if (!f) {
                return;
            }
            if (type === 'image' && f.type && f.type.indexOf('image/') === 0) {
                var img = document.createElement('img');
                img.alt = '';
                img.className = 'wa-tpl-media-thumb-img';
                var u = URL.createObjectURL(f);
                img.src = u;
                img.onload = function () { try { URL.revokeObjectURL(u); } catch (e) {} };
                thumbWrap.appendChild(img);
            } else if (type === 'video' && f.type && f.type.indexOf('video/') === 0) {
                var v = document.createElement('video');
                v.className = 'wa-tpl-media-thumb-vid';
                v.muted = true;
                v.playsInline = true;
                thumbWrap._videoUrl = URL.createObjectURL(f);
                v.src = thumbWrap._videoUrl;
                thumbWrap.appendChild(v);
            } else {
                var ph = document.createElement('div');
                ph.className = 'wa-tpl-media-thumb-doc';
                ph.innerHTML = '<i class="fas fa-file-alt"></i>';
                thumbWrap.appendChild(ph);
            }
        }

        function syncFileRow() {
            var f = fileInput.files && fileInput.files[0];
            if (f) {
                nameEl.textContent = f.name;
                sizeEl.textContent = humanSize(f.size);
                renderThumb(f);
                fileRow.style.display = 'flex';
                drop.style.display = 'none';
            } else {
                renderThumb(null);
                nameEl.textContent = '';
                sizeEl.textContent = '';
                fileRow.style.display = 'none';
                drop.style.display = '';
            }
            updateHeaderPreview();
        }

        function openPicker() {
            fileInput.click();
        }

        drop.querySelector('.wa-tpl-btn-choose-media').addEventListener('click', openPicker);
        btnReplace.addEventListener('click', openPicker);
        btnRemove.addEventListener('click', function () {
            fileInput.value = '';
            syncFileRow();
        });

        drop.addEventListener('dragover', function (e) {
            e.preventDefault();
            e.stopPropagation();
            drop.classList.add('wa-tpl-media-drop--hover');
        });
        drop.addEventListener('dragleave', function (e) {
            e.preventDefault();
            drop.classList.remove('wa-tpl-media-drop--hover');
        });
        drop.addEventListener('drop', function (e) {
            e.preventDefault();
            e.stopPropagation();
            drop.classList.remove('wa-tpl-media-drop--hover');
            var f = e.dataTransfer.files && e.dataTransfer.files[0];
            if (!f) return;
            var ok = false;
            if (type === 'image' && f.type && f.type.indexOf('image/') === 0) ok = true;
            if (type === 'video' && f.type && f.type.indexOf('video/') === 0) ok = true;
            if (type === 'doc') {
                var ext = (f.name.split('.').pop() || '').toLowerCase();
                if (['pdf', 'doc', 'docx'].indexOf(ext) >= 0) ok = true;
                var ct = (f.type || '').toLowerCase();
                if (ct.indexOf('pdf') >= 0 || ct.indexOf('word') >= 0 || ct.indexOf('msword') >= 0) ok = true;
            }
            if (!ok) return;
            try {
                var dt = new DataTransfer();
                dt.items.add(f);
                fileInput.files = dt.files;
            } catch (err) {
                console.warn('Drag-drop set files not supported', err);
            }
            syncFileRow();
        });

        fileInput.onchange = syncFileRow;
        syncFileRow();
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
                waHeader.innerHTML = `<img src="${url}" alt="" style="max-width:100%;border-radius:8px;display:block;">`;
            } else waHeader.innerHTML = '';
        } else if (currentMode === 'video') {
            const file = fileVideo ? fileVideo.files[0] : null;
            if (file) {
                const url = URL.createObjectURL(file);
                currentObjectURL = url;
                waHeader.innerHTML = `<video src="${url}" controls muted playsinline style="max-width:100%;border-radius:8px;display:block;max-height:200px;"></video>`;
            } else {
                waHeader.innerHTML = '<span class="small-muted" style="color:#64748b;">No video selected</span>';
            }
        } else if (currentMode === 'doc') {
            const file = fileDoc ? fileDoc.files[0] : null;
            if (file) {
                waHeader.innerHTML = `<div style="display:flex;align-items:center;gap:10px;padding:10px;background:#f8fafc;border-radius:8px;color:#0f172a;"><span style="font-size:1.5rem;">📄</span><div style="font-size:13px;font-weight:600;word-break:break-all;">${escapeHtml(file.name)}</div></div>`;
            } else {
                waHeader.innerHTML = '<span class="small-muted" style="color:#64748b;">No document selected</span>';
            }
        } else {
            waHeader.innerHTML = '';
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

        if (waBody) waBody.innerHTML = previewText ? nl2br(escapeHtml(previewText)) : '<span style="color:#999;">preview</span>';
        if (bodyCount) bodyCount.textContent = value.length;
        
        syncVariablesWithBody();
    }

    // متغير خارجي لحفظ حالة المتغيرات السابقة
let lastVarsJson = '';

function syncVariablesWithBody() {
    const text = bodyText ? bodyText.value : '';
    
    // البحث عن {{1}} أو [[1]]
    const re = /\[\[\s*(\d+)\s*\]\]|\{\{\s*(\d+)\s*\}\}/g;
    const nums = new Set();
    let m;
    while ((m = re.exec(text)) !== null) {
        nums.add(parseInt(m[1] || m[2], 10));
    }
    
    // ترتيب الأرقام
    const found = Array.from(nums).sort((a, b) => a - b);

    // 🔥 الحل السحري هنا: التحقق هل تغيرت هيكلة المتغيرات أم لا؟
    // نقارن المصفوفة الحالية بالمصفوفة السابقة
    const currentVarsJson = JSON.stringify(found);

    if (currentVarsJson === lastVarsJson) {
        // إذا لم تتغير قائمة الأرقام (مثلاً 1, 2 ما زالت 1, 2)
        // لا تفعل شيئاً واخرج فوراً لحماية التركيز (Focus)
        return; 
    }

    // تحديث الحالة السابقة بالجديدة
    lastVarsJson = currentVarsJson;

    // ---------------------------------------------------------
    // بقية الكود يعمل فقط إذا تغيرت الأرقام (أضيف متغير جديد أو حذف)
    // ---------------------------------------------------------

    if (found.length === 0) {
        bodyVarsWrap.innerHTML = `<button type="button" id="insert_var_btn" class="upload-btn">Add Variable {{1}}</button>`;
        document.getElementById('insert_var_btn')?.addEventListener('click', () => insertAtCursor(bodyText, '{{1}}'));
        return;
    }

    let html = '<div style="display:flex;flex-direction:column;gap:8px;">';
    found.forEach(i => {
        // نحاول الحفاظ على القيمة القديمة إذا كانت موجودة
        const val = bodySamples[String(i)] || '';
        html += `
            <div style="display:flex;gap:8px;align-items:center;">
                <label style="min-width:40px;">{{${i}}}</label>
                <input type="text" data-idx="${i}" class="body-sample-input" value="${escapeHtml(val)}" placeholder="Variable Example ${i}" style="flex:1;padding:6px;border-radius:4px;border:1px solid var(--border-color);background:var(--bg-primary);color:var(--text-primary);">
            </div>`;
    });
    
    // زر إضافة المتغير التالي
    const nextNum = (found.length > 0 ? Math.max(...found) : 0) + 1;
    html += `<button type="button" id="add_next_var" class="upload-btn" style="margin-top:5px;">New Variable {{${nextNum}}}</button></div>`;
    
    // هنا فقط يتم تحديث HTML مما قد يضيع التركيز، لكن هذا يحدث فقط عند إضافة متغير جديد في النص الأصلي
    bodyVarsWrap.innerHTML = html;

    // إعادة ربط الأحداث
    bodyVarsWrap.querySelectorAll('.body-sample-input').forEach(inp => {
        inp.addEventListener('input', (e) => {
            // تحديث الكائن bodySamples
            bodySamples[e.target.dataset.idx] = e.target.value;
            
            // هام: تأكد أن updateBodyPreview لا تستدعي syncVariablesWithBody مرة أخرى!
            if (typeof updateBodyPreview === 'function') {
                updateBodyPreview(); 
            }
        });
    });

    document.getElementById('add_next_var')?.addEventListener('click', () => {
        const next = Math.max(...found) + 1;
        insertAtCursor(bodyText, `{{${next}}}`);
        // ملاحظة: insertAtCursor ستغير النص، مما سيستدعي هذه الدالة مرة أخرى تلقائياً
        // وسيتم تحديث الـ HTML لإظهار الحقل الجديد
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
        const t = (type || 'quick_reply').toString().toLowerCase();
        return { type: t, text: '', url: '', phone: '' };
    }

    function renderButtonsList() {
        if (!buttonsListWrap) return;
        buttonsListWrap.innerHTML = '';
        
        buttons.forEach((btn, idx) => {
            const bt = (btn.type || 'quick_reply').toString().toLowerCase();
            const item = document.createElement('div');
            item.className = 'buttons-list-item';
            item.innerHTML = `
                <span style="font-size:11px;padding:3px 8px;background:rgba(124,58,237,0.2);border-radius:6px;color:#c4b5fd;font-weight:600;text-transform:capitalize;">${escapeHtml(bt)}</span>
                <input type="text" placeholder="Button label" class="btn-text-input" value="${escapeHtml(btn.text)}" style="flex:1;padding:8px;border-radius:8px;border:1px solid var(--border-color);background:var(--background);color:var(--text-primary);">
                ${bt === 'url' ? `<input type="url" placeholder="https://..." class="btn-url-input" value="${escapeHtml(btn.url)}" style="flex:1;padding:8px;border-radius:8px;border:1px solid var(--border-color);background:var(--background);color:var(--text-primary);">` : ''}
                ${bt === 'call' ? `<input type="tel" placeholder="+212..." class="btn-phone-input" value="${escapeHtml(btn.phone)}" style="flex:1;padding:8px;border-radius:8px;border:1px solid var(--border-color);background:var(--background);color:var(--text-primary);">` : ''}
                ${bt === 'copy' ? `<span class="small-muted" style="flex:1;font-size:11px;">Sample text for Meta review (user copies this pattern)</span>` : ''}
                <button type="button" class="btn-remove" aria-label="Remove" style="color:#f87171;border:none;background:transparent;cursor:pointer;font-size:1.1rem;">✕</button>
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
            b.textContent = btn.text || 'add text';
            b.style.cssText = "background:white;color:#00a884;text-align:center;padding:10px;margin-top:5px;border-radius:6px;font-weight:bold;box-shadow:0 1px 1px rgba(0,0,0,0.1);cursor:pointer;";
            waButtons.appendChild(b);
        });
    }

    function extractBodyPlaceholderOrder(text) {
        const re = /\{\{\s*(\d+)\s*\}\}|\[\[\s*(\d+)\s*\]\]/g;
        const nums = new Set();
        let m;
        while ((m = re.exec(text || '')) !== null) {
            nums.add(parseInt(m[1] || m[2], 10));
        }
        return Array.from(nums).sort((a, b) => a - b);
    }

    function buildBodySamplesPayload() {
        const text = bodyText ? bodyText.value : '';
        const order = extractBodyPlaceholderOrder(text);
        return order.map((n) => ({
            type: 'text',
            text: (bodySamples[String(n)] || '').trim() || `sample_${n}`,
        }));
    }

    function showTemplateFormError(msg) {
        if (!errorBox) {
            alert(msg);
            return;
        }
        errorBox.textContent = msg;
        errorBox.style.display = 'block';
        errorBox.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    // --- 3. إرسال البيانات (Submit) ---
    async function submitTemplate(e) {
        if(e) e.preventDefault();
        
        if(saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Submitting…'; }
        if(errorBox) { errorBox.style.display = 'none'; }

        const name = (document.getElementById('template_name')?.value || '').trim();
        const body = (bodyText?.value || '').trim();

        if (!name || !body) {
            showTemplateFormError('Please enter a template name and message body.');
            if(saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Submit to Meta'; }
            return;
        }

        if (!window.currentChannelId || window.currentChannelId === 'null') {
            showTemplateFormError('Select a WhatsApp channel first.');
            if(saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Submit to Meta'; }
            return;
        }

        const formData = new FormData();
        formData.append('name', name);
        formData.append('category', document.getElementById('template_category_select')?.value || 'utility');
        formData.append('language', document.getElementById('template_language')?.value || 'ar');
        formData.append('body', body);
        formData.append('footer', footerEl?.value || '');
        formData.append('header_type', currentMode);
        formData.append('channel_id', window.currentChannelId);
        formData.append('status', document.getElementById('template_status')?.value || 'draft');
        const updatedEl = document.getElementById('template_updated');
        if (updatedEl && updatedEl.value) formData.append('updated', updatedEl.value);

        if (currentMode === 'text') {
            const ta = inputArea ? inputArea.querySelector('textarea') : null;
            if (ta && ta.value.trim()) formData.append('header_text', ta.value.trim());
        } else if (currentMode === 'image' && fileImage?.files[0]) {
            formData.append('header_image', fileImage.files[0]);
        } else if (currentMode === 'video' && fileVideo?.files[0]) {
            formData.append('header_video', fileVideo.files[0]);
        } else if (currentMode === 'doc' && fileDoc?.files[0]) {
            formData.append('header_document', fileDoc.files[0]);
        }

        formData.append('buttons', JSON.stringify(buttons));
        formData.append('body_samples', JSON.stringify(buildBodySamplesPayload()));

        const editingId = editingInput?.value;
        const url = editingId 
            ? `/discount/whatssapAPI/api/templates/${editingId}/` 
            : API_URLS.createTemplate;

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: { 'X-CSRFToken': getCsrfToken() },
                credentials: 'same-origin',
                body: formData
            });

            const data = await response.json().catch(() => ({}));

            if (response.ok && data.success !== false) {
                if(createSection) createSection.style.display = 'none';
                if(tableWrap) tableWrap.style.display = 'block';
                if (createBtn) createBtn.style.display = '';
                window.loadTemplates();
            } else {
                let msg = data.error || data.errors;
                if (Array.isArray(msg)) msg = msg.join('. ');
                if (typeof msg === 'object' && msg !== null) msg = JSON.stringify(msg);
                if (!msg) msg = 'Could not save template.';
                if (data.detail && data.detail.error) {
                    const me = data.detail.error;
                    msg += typeof me === 'object' ? (' — ' + (me.message || JSON.stringify(me))) : (' — ' + me);
                }
                showTemplateFormError(String(msg));
            }
        } catch (error) {
            showTemplateFormError(error.message || 'Network error');
        } finally {
            if(saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Submit to Meta'; }
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
                        type: (b.type || 'quick_reply').toString().toLowerCase(),
                        text: b.text || '',
                        url: b.url || '',
                        phone: b.phone || b.phone_number || ''
                    }));
                }
                renderButtonsList();
                updateBodyPreview();
            }
        } catch(e) {
            console.error(e);
            alert("Error fetching template data.");
        }
    };

    function resetForm() {
        if(editingInput) editingInput.value = '';
        document.getElementById('template_name').value = '';
        bodyText.value = '';
        if (fileImage) fileImage.value = '';
        if (fileVideo) fileVideo.value = '';
        if (fileDoc) fileDoc.value = '';
        revokeObjectURL();
        buttons = [];
        renderButtonsList();
        updateBodyPreview();
        updateHeaderHintVisibility(true);
    }

    // --- تهيئة الصفحة ---
    document.addEventListener('DOMContentLoaded', function() {
        // الأحداث
        if (btnText) btnText.addEventListener('click', () => { setActiveTab(btnText); currentMode = 'text'; showTextInput(); });
        if (btnImage) btnImage.addEventListener('click', () => { setActiveTab(btnImage); currentMode = 'image'; showFileUpload('image'); });
        if (btnVideo) btnVideo.addEventListener('click', () => { setActiveTab(btnVideo); currentMode = 'video'; showFileUpload('video'); });
        if (btnDoc) btnDoc.addEventListener('click', () => { setActiveTab(btnDoc); currentMode = 'doc'; showFileUpload('doc'); });
        updateHeaderHintVisibility(true);
        
        if (bodyText) bodyText.addEventListener('input', updateBodyPreview);
        if (footerEl) footerEl.addEventListener('input', () => { if(waFooter) waFooter.textContent = footerEl.value; });

        if (addButtonBtn) addButtonBtn.addEventListener('click', () => {
            if (buttons.length >= MAX_BUTTONS) return alert(`You can't add more than ${MAX_BUTTONS} buttons.`);
            const type = newButtonType ? newButtonType.value : 'quick_reply';
            buttons.push(createButtonObject(type));
            renderButtonsList();
        });

        if (createBtn) createBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            createSection.style.display = 'block';
            tableWrap.style.display = 'none';
            createBtn.style.display = 'none';
            resetForm();
            showTextInput();
        });

        if (cancelBtn) cancelBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            createSection.style.display = 'none';
            tableWrap.style.display = 'block';
            if (createBtn) createBtn.style.display = '';
        });

        if (saveBtn) saveBtn.addEventListener('click', submitTemplate);

        if (refreshBtn) refreshBtn.addEventListener('click', async () => {
            if (!window.currentChannelId || window.currentChannelId === 'null') {
                alert('Select a channel first.');
                return;
            }
            refreshBtn.disabled = true;
            const label = refreshBtn.querySelector('span') || refreshBtn;
            const prev = label.textContent;
            label.textContent = 'Syncing…';
            try {
                const r = await fetch(`${API_URLS.syncTemplates}?channel_id=${window.currentChannelId}`, {
                    credentials: 'same-origin',
                    headers: { 'Accept': 'application/json', 'X-CSRFToken': getCsrfToken() }
                });
                const j = await r.json().catch(() => ({}));
                if (!r.ok || j.success === false) {
                    throw new Error(j.error || 'Sync failed');
                }
                window.loadTemplates();
            } catch(e) {
                alert(e.message || 'Error syncing templates.');
                console.error(e);
            }             finally {
                refreshBtn.disabled = false;
                const sp = refreshBtn.querySelector('span');
                if (sp) sp.textContent = 'Sync templates';
                else refreshBtn.textContent = prev;
            }
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
  if (!wrapper) return;
    

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

/**
 * When the customer sends a message (websocket) while this chat is open, remove the
 * send-failure banner and show the normal composer again.
 */
window.dismissSendErrorBannerForChat = function (phone) {
  const activePhone = (typeof window.getCurrentChatPhone === 'function')
    ? window.getCurrentChatPhone()
    : null;
  if (!activePhone || phone == null || phone === '') return;
  const cleanIncoming = String(phone).replace(/\D/g, '');
  const cleanActive = String(activePhone).replace(/\D/g, '');
  if (!cleanIncoming || cleanIncoming !== cleanActive) return;

  const wrapper = document.querySelector('.cls3741_chat_input_wrapper');
  if (!wrapper) return;
  const banner = wrapper.querySelector('.error-banner');
  if (banner) banner.remove();

  const inputContainer = document.querySelector('.cls3741_input_container');
  if (inputContainer) inputContainer.classList.remove('d-none');
};





     
 
  




// on time update agent_handling msgs
// متغير لتخزين المحادثة الحالية التي ينظر إليها المستخدم
let currentOpenChatId = null;
// قائمة لتخزين المتواجدين حالياً في المحادثة (لتجنب التكرار)
let activeViewers = new Set(); 

// 1. دالة يتم استدعاؤها عند فتح أي محادثة (يجب إضافتها لحدث النقر على جهة الاتصال)
window.notifyChatEnter = function(chatId) {
    if (currentOpenChatId && currentOpenChatId !== chatId) {
        notifyChatLeave(currentOpenChatId);
    }

    currentOpenChatId = chatId;
    activeViewers.clear(); // تصفير قائمة المشاهدين للمحادثة الجديدة
    hideCollisionAlert();  // إخفاء التنبيه القديم
    const payload= {
            action: 'enter',
            phone_number: chatId  
        }
    // إرسال إشارة الدخول
    if (window.ChatSocket && window.ChatSocket.socket && window.ChatSocket.socket.readyState === WebSocket.OPEN) {
     
        window.ChatSocket.send(
            'chat_activity' 
             , payload
        );
    }
    // window.ChatSocket.send(
    //     'chat_activity', 
    //     payload
    // );

}

// 2. دالة الخروج (عند الانتقال لمحادثة أخرى أو إغلاق الصفحة)
function notifyChatLeave(chatId) {
     const payload= {
        action: 'leave',
        phone_number: chatId
    }
    if (!chatId) return;
    
    if (window.ChatSocket && window.ChatSocket.socket && window.ChatSocket.socket.readyState === WebSocket.OPEN) {
     
        window.ChatSocket.send(
            'chat_activity' 
             , payload
        );
    }
}

// 3. معالجة التحديثات القادمة من السيرفر
// أضف هذا الجزء داخل chatSocket.onmessage
/*
if (data.data_type === 'collision_update') {
    handleCollisionUpdate(data.payload);
}
*/
currentUserId = document.getElementById('current_user_id').getAttribute('data-user-id');
// window.handleCollisionUpdate = function(payload) {
//     // نتجاهل التحديثات التي تخصني أنا (أعرف أنني دخلت!)
//     if (payload.user_id == currentUserId) return;
     
//     // نتأكد أن التحديث يخص المحادثة المفتوحة حالياً
//     if (payload.chat_id != currentOpenChatId) return;

//     if (payload.action === 'enter') {
//         // شخص دخل -> نضيفه للقائمة
//         activeViewers.add(payload.user_name);
        
//         // 🔥 نقطة ذكية: إذا دخل شخص جديد وأنا موجود قبله،
//         // يجب أن أخبره أنني موجود أيضاً (Sync Presence)
//         // نرسل إشارة دخول مرة أخرى (بدون تكرار المنطق) ليعرف بوجودي
//         // (يمكن تحسين هذا الجزء لاحقاً ليكون تلقائياً من الباك إند)
        
//     } else if (payload.action === 'leave') {
//         // شخص خرج -> نحذفه من القائمة
//         activeViewers.delete(payload.user_name);
//     }

//     // تحديث واجهة التنبيه
//     updateCollisionUI();
// }


window.handleCollisionUpdate = function(payload){
    // 1. تحويل الـ IDs لنصوص لضمان المقارنة الصحيحة
    const incomingChatId = String(payload.chat_id);
    const currentChatId = String(currentOpenChatId);
    const incomingUserId = String(payload.user_id);
    const myId = String(currentUserId); // تأكد أن لديك هذا المتغير متاحاً

    // التحقق من أن التحديث يخص المحادثة المفتوحة حالياً
    // إذا كان التحديث لمحادثة أخرى، نتجاهله
    if (incomingChatId !== currentChatId) return;

    // ----------------------------------------------------
    // الحالة 1: شخص جديد دخل (Enter)
    // ----------------------------------------------------
    if (payload.action === 'enter') {
        // إذا كنت أنا من دخل، لا تفعل شيئاً
        if (incomingUserId === myId) return;

        // 1. أضف الشخص لقائمتي
        activeViewers.add(payload.user_name);
        
        // 2. 🔥 هذا هو الحل للمشكلة 🔥
        // بما أن شخصاً جديداً دخل وأنا موجود قبله
        // يجب أن أرسل له إشارة "أنا هنا أيضاً" لكي يراني هو
        sendPresenceSync(currentChatId);
    } 
    
    // ----------------------------------------------------
    // الحالة 2: شخص يغادر (Leave)
    // ----------------------------------------------------
    else if (payload.action === 'leave') {
        if (incomingUserId === myId) return;
        activeViewers.delete(payload.user_name);
    }
    
    // ----------------------------------------------------
    // الحالة 3: استلام إشارة الوجود من القدامى (Sync)
    // ----------------------------------------------------
    else if (payload.action === 'presence_sync') {
         
        if (incomingUserId === myId) return;
        
        // أضيفهم لقائمتي فقط، ولا أرد عليهم (لتجنب حلقة لا نهائية)
        activeViewers.add(payload.user_name);
    }

    // أخيراً: تحديث الواجهة (الشريط الأصفر)
    updateCollisionUI();
}
            
// --- دالة مساعدة لإرسال إشارة الوجود ---
function sendPresenceSync(chatId) {
    const payload = {
                action: 'presence_sync',
                phone_number : chatId
    }
    if (window.ChatSocket && window.ChatSocket.socket && window.ChatSocket.socket.readyState === WebSocket.OPEN) {
     
        window.ChatSocket.send(
            'chat_activity' 
             , payload
        );
    }
}




function updateCollisionUI() {

    const alertBar = $('#collision_alert_bar');


    const alertText = $('#collision_text');
    
    if (activeViewers.size > 0) {
        const names = Array.from(activeViewers).join(', ');
        const verb = activeViewers.size > 1 ? 'are' : 'is';
        

        alertText.html(`⚠️ <strong>${names}</strong> ${verb} viewing this chat now.`);
        alertBar.slideDown(200);
    } else {
        alertBar.slideUp(200);
    }
}

function hideCollisionAlert() {
    $('#collision_alert_bar').hide();
    activeViewers.clear();
}