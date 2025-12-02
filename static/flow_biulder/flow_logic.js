// jsPlumb.ready(function() {

//     // 1. تهيئة jsPlumb
//     var instance = jsPlumb.getInstance({
//         Container: "flow-container",
//         Connector: "Flowchart",
//         Endpoint: ["Dot", { radius: 5 }],
//         PaintStyle: { stroke: "#61B7CF", strokeWidth: 2 },
//         HoverPaintStyle: { stroke: "#1e8151" },
//         EndpointStyle: { fill: "#61B7CF" },
//         EndpointHoverStyle: { fill: "#1e8151" }
//     });

//     // إعدادات نقاط الاتصال
//     var sourceEndpointStyle = {
//         isSource: true,
//         anchor: "Bottom",
//         maxConnections: 5,
//     };
//     var targetEndpointStyle = {
//         isTarget: true,
//         anchor: "Top",
//         maxConnections: 1,
//     };

//     var nodeCounter = 0; // عداد لإنشاء معرفات فريدة

//     // 2. دالة لإنشاء عقدة جديدة (Node)
//     function createNode(id, type, top, left, label) {
//         // إنشاء العنصر HTML
//         var newNode = $('<div>')
//             .attr('id', id)
//             .addClass('node')
//             .addClass('node-' + type) // لإضافة تنسيق مختلف
//             .css({ top: top + 'px', left: left + 'px' })
//             .text(label || type);
        
//         $("#flow-container").append(newNode);

//         // جعل العقدة قابلة للسحب
//         instance.draggable(newNode, {
//             containment: "parent"
//         });

//         // إضافة نقاط الاتصال
//         instance.addEndpoint(newNode, targetEndpointStyle); // نقطة الدخول (أعلى)
//         instance.addEndpoint(newNode, sourceEndpointStyle); // نقطة الخروج (أسفل)
        
//         return newNode;
//     }

//     // 3. دالة لتحميل التدفق (Load Flow)
//     function loadFlow() {
//         if (!initialFlowData || !initialFlowData.nodes) {
//             console.log("No initial data to load.");
//             return;
//         }

//         var nodes = initialFlowData.nodes;
//         var connections = initialFlowData.connections;

//         // تحميل العقد (Nodes)
//         nodes.forEach(function(node) {
//             createNode(node.id, node.type, node.top, node.left, node.label);
//             // تحديث العداد لضمان عدم تكرار المعرفات
//             var idNum = parseInt(node.id.split('-')[1]);
//             if (idNum > nodeCounter) {
//                 nodeCounter = idNum;
//             }
//         });

//         // تحميل الروابط (Connections)
//         connections.forEach(function(conn) {
//             instance.connect({
//                 source: conn.sourceId,
//                 target: conn.targetId,
//             });
//         });
//     }

//     // 4. دالة لحفظ التدفق (Save Flow)
//     function saveFlow() {
//         var flowData = {
//             nodes: [],
//             connections: []
//         };

//         // حفظ العقد ومواقعها
//         $(".node").each(function(index, element) {
//             var $el = $(element);
//             flowData.nodes.push({
//                 id: $el.attr('id'),
//                 type: $el.attr('class').split(' ')[1].replace('node-', ''), // استخراج النوع
//                 label: $el.text(),
//                 top: parseInt($el.css("top")),
//                 left: parseInt($el.css("left"))
//             });
//         });

//         // حفظ الروابط
//         flowData.connections = instance.getConnections().map(function(conn) {
//             return {
//                 sourceId: conn.sourceId,
//                 targetId: conn.targetId
//             };
//         });

//         // إرسال البيانات إلى Django API
//         fetch(saveUrl, {
//             method: 'POST',
//             headers: {
//                 'Content-Type': 'application/json',
//                 'X-CSRFToken': csrfToken // إرسال رمز الحماية
//             },
//             body: JSON.stringify({ flow_data: flowData })
//         })
//         .then(response => response.json())
//         .then(data => {
//             if (data.status === 'success') {
//                 alert("Flow Saved Successfully!");
//             } else {
//                 alert("Error saving flow: " + data.message);
//             }
//         })
//         .catch(error => {
//             console.error('Error:', error);
//             alert("An error occurred while saving.");
//         });
//     }

//     // 5. تفعيل السحب والإفلات من الشريط الجانبي (Sidebar)
//     $(".node-source").on("click", function() {
//         var type = $(this).data('type');
//         var label = $(this).text();
//         var newNodeId = "node-" + (++nodeCounter);
        
//         // إنشاء عقدة جديدة في موقع افتراضي
//         createNode(newNodeId, type, 150, 250, label);
//     });

//     // 6. ربط زر الحفظ
//     $("#save-button").on("click", saveFlow);

//     // 7. البدء بتحميل التدفق الموجود
//     loadFlow();
// });


































// //     class FlowBuilder {
// //     constructor() {
// //         this.csrfToken = this.getCsrfToken();
// //         this.selectedNode = null;
// //         this.nodeCounter = 0;
// //         this.currentFlowId = null;
// //         this.jsPlumbInstance = null;
// //         this.connectionMode = false;
// //         this.connectionSource = null;
// //         this.zoomLevel = 1.0;
// //         this.zoomStep = 0.1;
// //         this.minZoom = 0.3;
// //         this.maxZoom = 3.0;
        
// //         this.nodeTemplates = {
// //             'text-message': this.createTextMessageNode.bind(this),
// //             'media-message': this.createMediaMessageNode.bind(this),
// //             'condition': this.createConditionNode.bind(this),
// //             'delay': this.createDelayNode.bind(this),
// //             'trigger': this.createTriggerNode.bind(this),
// //             'buttons-message': this.createButtonsMessageNode.bind(this),
// //             'list-message': this.createListMessageNode.bind(this),
// //             'webhook': this.createWebhookNode.bind(this),
// //             'add-contact': this.createAddContactNode.bind(this),
// //             'update-contact': this.createUpdateContactNode.bind(this),
// //             'add-tags': this.createAddTagsNode.bind(this),
// //             'remove-tags': this.createRemoveTagsNode.bind(this)
// //         };
        
// //         this.initializeElements();
// //         this.initializeEventListeners();
// //         this.initializeJsPlumb();
// //         this.setupDragAndDrop();
// //         this.initializeZoom();
// //         this.updateStats();
// //     }

// //     getCsrfToken() {
// //         const cookieValue = document.cookie
// //             .split('; ')
// //             .find(row => row.startsWith('csrftoken='))
// //             ?.split('=')[1];
// //         return cookieValue || '';
// //     }

// //     initializeElements() {
// //         this.flowCanvas = document.getElementById('flow-canvas');
// //         this.saveFlowBtn = document.getElementById('save-flow-btn');
// //         this.loadFlowBtn = document.getElementById('load-flow-btn');
// //         this.clearBtn = document.getElementById('clear-btn');
// //         this.layoutBtn = document.getElementById('layout-btn');
// //         this.flowSelect = document.getElementById('flow-select');
// //         this.addVariableBtn = document.getElementById('add-variable-btn');
// //         this.sampleFlowBtn = document.getElementById('sample-flow-btn');
// //         this.loadExistingBtn = document.getElementById('load-existing-btn');
        
// //         this.nodeCountEl = document.getElementById('node-count');
// //         this.connectionCountEl = document.getElementById('connection-count');
// //     }

// //     initializeEventListeners() {
// //         this.saveFlowBtn?.addEventListener('click', () => this.saveFlow());
// //         this.loadFlowBtn?.addEventListener('click', () => this.loadFlow());
// //         this.clearBtn?.addEventListener('click', () => this.clearCanvas());
// //         this.layoutBtn?.addEventListener('click', () => this.autoLayout());
// //         this.addVariableBtn?.addEventListener('click', () => this.addVariable());
// //         this.sampleFlowBtn?.addEventListener('click', () => this.addSampleFlow());
// //         this.loadExistingBtn?.addEventListener('click', () => this.loadFlows());
        
// //         this.loadFlows();
// //     }

// //     initializeJsPlumb() {
// //         if (typeof jsPlumb === 'undefined') {
// //             console.error('jsPlumb not loaded');
// //             setTimeout(() => this.initializeJsPlumb(), 100);
// //             return;
// //         }

// //         this.jsPlumbInstance = jsPlumb.getInstance({
// //             Connector: ["Flowchart", { cornerRadius: 5 }],
// //             PaintStyle: { 
// //                 stroke: "#7C3AED", 
// //                 strokeWidth: 2,
// //                 outlineStroke: "transparent",
// //                 outlineWidth: 10
// //             },
// //             EndpointStyle: { 
// //                 fill: "#7C3AED",
// //                 radius: 5
// //             },
// //             HoverPaintStyle: { 
// //                 stroke: "#10B981", 
// //                 strokeWidth: 3 
// //             },
// //             ConnectionOverlays: [
// //                 ["Arrow", { 
// //                     location: 1, 
// //                     width: 12, 
// //                     length: 12 
// //                 }]
// //             ],
// //             Container: "flow-canvas"
// //         });

// //         this.jsPlumbInstance.bind("connection", (info) => {
// //             this.updateStats();
// //             this.saveNodePositions();
// //         });

// //         this.jsPlumbInstance.bind("connectionDetached", (info) => {
// //             this.updateStats();
// //         });

// //         this.jsPlumbInstance.bind("connection", (conn) => {
// //             conn.bind("click", (connection, originalEvent) => {
// //                 if (confirm('Delete this connection?')) {
// //                     this.jsPlumbInstance.deleteConnection(connection);
// //                     this.showNotification('Connection deleted', 'success');
// //                 }
// //             });
// //         });
// //     }

// //     setupDragAndDrop() {
// //         const components = document.querySelectorAll('.component-item');
        
// //         components.forEach(component => {
// //             component.addEventListener('dragstart', (e) => {
// //                 e.dataTransfer.setData('component-type', component.dataset.type);
// //                 e.dataTransfer.effectAllowed = 'copy';
// //             });
// //         });

// //         this.flowCanvas.addEventListener('dragover', (e) => {
// //             e.preventDefault();
// //             e.dataTransfer.dropEffect = 'copy';
// //         });

// //         this.flowCanvas.addEventListener('drop', (e) => {
// //             e.preventDefault();
// //             const componentType = e.dataTransfer.getData('component-type');
// //             const rect = this.flowCanvas.getBoundingClientRect();
// //             const x = e.clientX - rect.left - 140;
// //             const y = e.clientY - rect.top - 50;
            
// //             this.createNode(componentType, x, y);
// //         });
// //     }

// //     createNode(type, x, y) {
// //         this.nodeCounter++;
// //         const nodeId = `node-${this.nodeCounter}`;
        
// //         const node = document.createElement('div');
// //         node.className = 'flow-node';
// //         node.id = nodeId;
// //         node.style.left = x + 'px';
// //         node.style.top = y + 'px';
// //         node.dataset.nodeType = type;
        
// //         const emptyState = this.flowCanvas.querySelector('.empty-state');
// //         if (emptyState) {
// //             emptyState.remove();
// //         }
        
// //         const templateFunction = this.nodeTemplates[type];
// //         if (templateFunction) {
// //             node.innerHTML = templateFunction(nodeId);
// //         } else {
// //             node.innerHTML = this.createTextMessageNode(nodeId);
// //         }

// //         this.flowCanvas.appendChild(node);
// //         this.initializeNode(nodeId);
// //         this.updateStats();
// //         return nodeId;
// //     }

// //     createTextMessageNode(nodeId) {
// //         return `
// //             <div class="node-header">
// //                 <div class="node-icon">📝</div>
// //                 <div class="node-title">Text Message</div>
// //                 <div class="node-type">text-message</div>
// //             </div>
// //             <div class="node-body">
// //                 <div class="node-content">
// //                     <textarea class="node-input message-content" placeholder="Enter message text..." rows="3" data-field="content">Hello! How can I help you?</textarea>
// //                 </div>
// //                 <div class="node-properties">
// //                     <div class="node-property">
// //                         <span>Delay:</span>
// //                         <input type="number" value="0" min="0" class="node-input delay-value" data-field="delay" style="width: 60px;"> seconds
// //                     </div>
// //                 </div>
// //             </div>
// //             <div class="node-footer">
// //                 <button class="btn btn-secondary btn-sm connect-btn" data-node-id="${nodeId}">Connect</button>
// //                 <button class="btn btn-danger btn-sm delete-node-btn" data-node-id="${nodeId}">Delete</button>
// //             </div>
// //         `;
// //     }

// //     createMediaMessageNode(nodeId) {
// //         return `
// //             <div class="node-header">
// //                 <div class="node-icon">🖼️</div>
// //                 <div class="node-title">Media Message</div>
// //                 <div class="node-type">media-message</div>
// //             </div>
// //             <div class="node-body">
// //                 <div class="node-content">
// //                     <textarea class="node-input caption-content" placeholder="Caption (optional)..." rows="2" data-field="caption"></textarea>
// //                 </div>
// //                 <div class="form-group">
// //                     <select class="node-input media-type-select" data-field="mediaType">
// //                         <option value="image">Image</option>
// //                         <option value="video">Video</option>
// //                         <option value="audio">Audio</option>
// //                         <option value="file">File</option>
// //                     </select>
// //                 </div>
// //                 <div class="form-group">
// //                     <input type="file" class="node-input media-file-input" data-field="mediaFile" accept="image/*,video/*,audio/*,.pdf">
// //                 </div>
// //                 <div class="node-properties">
// //                     <div class="node-property">
// //                         <span>Delay:</span>
// //                         <input type="number" value="0" min="0" class="node-input delay-value" data-field="delay" style="width: 60px;"> seconds
// //                     </div>
// //                 </div>
// //             </div>
// //             <div class="node-footer">
// //                 <button class="btn btn-secondary btn-sm connect-btn" data-node-id="${nodeId}">Connect</button>
// //                 <button class="btn btn-danger btn-sm delete-node-btn" data-node-id="${nodeId}">Delete</button>
// //             </div>
// //         `;
// //     }

// //     createConditionNode(nodeId) {
// //         return `
// //             <div class="node-header">
// //                 <div class="node-icon">🔀</div>
// //                 <div class="node-title">Condition</div>
// //                 <div class="node-type">condition</div>
// //             </div>
// //             <div class="node-body">
// //                 <div class="form-group">
// //                     <label class="form-label">Variable</label>
// //                     <input type="text" class="node-input condition-variable" data-field="variable" placeholder="Variable name">
// //                 </div>
// //                 <div class="form-group">
// //                     <label class="form-label">Value</label>
// //                     <input type="text" class="node-input condition-value" data-field="value" placeholder="Value to compare">
// //                 </div>
// //                 <div class="form-group">
// //                     <label class="form-label">Comparison Type</label>
// //                     <select class="node-input condition-operator" data-field="operator">
// //                         <option value="equals">Equals</option>
// //                         <option value="contains">Contains</option>
// //                         <option value="startsWith">Starts With</option>
// //                         <option value="endsWith">Ends With</option>
// //                         <option value="greaterThan">Greater Than</option>
// //                         <option value="lessThan">Less Than</option>
// //                     </select>
// //                 </div>
// //             </div>
// //             <div class="node-footer">
// //                 <button class="btn btn-secondary btn-sm connect-btn true-branch" data-node-id="${nodeId}" data-branch="true">Connect (True)</button>
// //                 <button class="btn btn-secondary btn-sm connect-btn false-branch" data-node-id="${nodeId}" data-branch="false">Connect (False)</button>
// //                 <button class="btn btn-danger btn-sm delete-node-btn" data-node-id="${nodeId}">Delete</button>
// //             </div>
// //         `;
// //     }

// //     createDelayNode(nodeId) {
// //         return `
// //             <div class="node-header">
// //                 <div class="node-icon">⏱️</div>
// //                 <div class="node-title">Delay</div>
// //                 <div class="node-type">delay</div>
// //             </div>
// //             <div class="node-body">
// //                 <div class="form-group">
// //                     <label class="form-label">Delay Duration</label>
// //                     <input type="number" class="node-input delay-duration" data-field="duration" value="5" min="0" max="3600">
// //                     <div class="text-muted" style="font-size: 0.75rem; margin-top: 0.25rem;">Seconds</div>
// //                 </div>
// //             </div>
// //             <div class="node-footer">
// //                 <button class="btn btn-secondary btn-sm connect-btn" data-node-id="${nodeId}">Connect</button>
// //                 <button class="btn btn-danger btn-sm delete-node-btn" data-node-id="${nodeId}">Delete</button>
// //             </div>
// //         `;
// //     }

// //     createTriggerNode(nodeId) {
// //         return `
// //             <div class="node-header">
// //                 <div class="node-icon">🔔</div>
// //                 <div class="node-title">Flow Trigger</div>
// //                 <div class="node-type">trigger</div>
// //             </div>
// //             <div class="node-body">
// //                 <div class="form-group">
// //                     <label class="form-label">Trigger Type</label>
// //                     <select class="node-input trigger-type" data-field="triggerType">
// //                         <option value="keyword">Keyword</option>
// //                         <option value="time">Scheduled Time</option>
// //                         <option value="event">Event</option>
// //                         <option value="webhook">Webhook</option>
// //                     </select>
// //                 </div>
// //                 <div class="trigger-conditions">
// //                     <div class="form-group">
// //                         <label class="form-label">Keywords</label>
// //                         <input type="text" class="node-input trigger-keywords" data-field="keywords" placeholder="Enter keywords separated by comma">
// //                     </div>
// //                 </div>
// //             </div>
// //             <div class="node-footer">
// //                 <button class="btn btn-secondary btn-sm connect-btn" data-node-id="${nodeId}">Connect</button>
// //                 <button class="btn btn-danger btn-sm delete-node-btn" data-node-id="${nodeId}">Delete</button>
// //             </div>
// //         `;
// //     }

// //     createButtonsMessageNode(nodeId) {
// //         return this.createTextMessageNode(nodeId).replace('Text Message', 'Interactive Buttons');
// //     }

// //     createListMessageNode(nodeId) {
// //         return this.createTextMessageNode(nodeId).replace('Text Message', 'Interactive List');
// //     }

// //     createWebhookNode(nodeId) {
// //         return this.createTextMessageNode(nodeId).replace('Text Message', 'Webhook');
// //     }

// //     createAddContactNode(nodeId) {
// //         return this.createTextMessageNode(nodeId).replace('Text Message', 'Add Contact');
// //     }

// //     createUpdateContactNode(nodeId) {
// //         return this.createTextMessageNode(nodeId).replace('Text Message', 'Update Contact');
// //     }

// //     createAddTagsNode(nodeId) {
// //         return this.createTextMessageNode(nodeId).replace('Text Message', 'Add Tags');
// //     }

// //     createRemoveTagsNode(nodeId) {
// //         return this.createTextMessageNode(nodeId).replace('Text Message', 'Remove Tags');
// //     }

// //     initializeNode(nodeId) {
// //         const node = document.getElementById(nodeId);
// //         if (!node || !this.jsPlumbInstance) return;

// //         this.jsPlumbInstance.draggable(nodeId, {
// //             grid: [10, 10],
// //             stop: () => this.saveNodePositions()
// //         });
        
// //         this.jsPlumbInstance.addEndpoint(nodeId, {
// //             anchor: "Right",
// //             endpoint: "Dot",
// //             paintStyle: { fill: "#7C3AED", radius: 5 },
// //             isSource: true,
// //             maxConnections: 10
// //         });
        
// //         this.jsPlumbInstance.addEndpoint(nodeId, {
// //             anchor: "Left", 
// //             endpoint: "Dot",
// //             paintStyle: { fill: "#10B981", radius: 5 },
// //             isTarget: true,
// //             maxConnections: 10
// //         });
        
// //         const connectBtns = node.querySelectorAll('.connect-btn');
// //         connectBtns.forEach(btn => {
// //             btn.addEventListener('click', (e) => {
// //                 e.stopPropagation();
// //                 const branch = e.target.dataset.branch;
// //                 this.connectNode(nodeId, branch);
// //             });
// //         });
        
// //         const deleteBtn = node.querySelector('.delete-node-btn');
// //         if (deleteBtn) {
// //             deleteBtn.addEventListener('click', (e) => {
// //                 e.stopPropagation();
// //                 this.removeNode(nodeId);
// //             });
// //         }
        
// //         node.addEventListener('click', (e) => {
// //             if (!e.target.closest('.connect-btn') && !e.target.closest('.delete-node-btn')) {
// //                 this.selectNode(nodeId);
// //             }
// //         });

// //         // إضافة مستمعات للتغييرات في الحقول
// //         const inputs = node.querySelectorAll('.node-input');
// //         inputs.forEach(input => {
// //             input.addEventListener('change', () => this.saveNodePositions());
// //             input.addEventListener('input', () => this.saveNodePositions());
// //         });
// //     }

//     // initializeZoom() {
//     //     this.createZoomControls();
//     //     this.setupZoomEvents();
//     // }

//     // createZoomControls() {
//     //     const zoomControls = document.createElement('div');
//     //     zoomControls.className = 'zoom-controls';
//     //     zoomControls.innerHTML = `
//     //         <div class="zoom-buttons">
//     //             <button class="btn btn-secondary btn-sm" id="zoom-out" title="Zoom Out (Ctrl + -)">
//     //                 <span>−</span>
//     //             </button>
//     //             <span class="zoom-level" id="zoom-level">100%</span>
//     //             <button class="btn btn-secondary btn-sm" id="zoom-in" title="Zoom In (Ctrl + +)">
//     //                 <span>+</span>
//     //             </button>
//     //             <button class="btn btn-secondary btn-sm" id="zoom-reset" title="Reset Zoom (Ctrl + 0)">
//     //                 <span>⟳</span>
//     //             </button>
//     //             <button class="btn btn-secondary btn-sm" id="zoom-fit" title="Fit to Content">
//     //                 <span>⤢</span>
//     //             </button>
//     //         </div>
//     //     `;
        
//     //     const header = document.querySelector('.header-actions');
//     //     if (header) {
//     //         header.appendChild(zoomControls);
            
//     //         document.getElementById('zoom-in').addEventListener('click', () => this.zoomIn());
//     //         document.getElementById('zoom-out').addEventListener('click', () => this.zoomOut());
//     //         document.getElementById('zoom-reset').addEventListener('click', () => this.zoomReset());
//     //         document.getElementById('zoom-fit').addEventListener('click', () => this.zoomToFit());
//     //     }
//     // }

//     // setupZoomEvents() {
//     //     this.flowCanvas.addEventListener('wheel', (e) => {
//     //         if (e.ctrlKey) {
//     //             e.preventDefault();
//     //             if (e.deltaY < 0) {
//     //                 this.zoomIn();
//     //             } else {
//     //                 this.zoomOut();
//     //             }
//     //         }
//     //     });

//     //     document.addEventListener('keydown', (e) => {
//     //         if (e.ctrlKey) {
//     //             if (e.key === '=' || e.key === '+') {
//     //                 e.preventDefault();
//     //                 this.zoomIn();
//     //             } else if (e.key === '-') {
//     //                 e.preventDefault();
//     //                 this.zoomOut();
//     //             } else if (e.key === '0') {
//     //                 e.preventDefault();
//     //                 this.zoomReset();
//     //             }
//     //         }
//     //     });
//     // }

//     // zoomIn() {
//     //     if (this.zoomLevel < this.maxZoom) {
//     //         this.zoomLevel += this.zoomStep;
//     //         this.applyZoom();
//     //     }
//     // }

//     // zoomOut() {
//     //     if (this.zoomLevel > this.minZoom) {
//     //         this.zoomLevel -= this.zoomStep;
//     //         this.applyZoom();
//     //     }
//     // }

//     // zoomReset() {
//     //     this.zoomLevel = 1.0;
//     //     this.applyZoom();
//     // }

//     // applyZoom() {
//     //     this.flowCanvas.style.transform = `scale(${this.zoomLevel})`;
//     //     this.flowCanvas.style.transformOrigin = '0 0';
        
//     //     const zoomLevelEl = document.getElementById('zoom-level');
//     //     if (zoomLevelEl) {
//     //         zoomLevelEl.textContent = `${Math.round(this.zoomLevel * 100)}%`;
//     //     }
        
//     //     if (this.jsPlumbInstance) {
//     //         this.jsPlumbInstance.setZoom(this.zoomLevel);
//     //         setTimeout(() => {
//     //             this.jsPlumbInstance.repaintEverything();
//     //         }, 10);
//     //     }
//     // }

//     // zoomToFit() {
//     //     const nodes = document.querySelectorAll('.flow-node');
//     //     if (nodes.length === 0) return;
        
//     //     this.zoomReset();
//     //     this.autoLayout();
//     // }

//     // updateStats() {
//     //     const nodeCount = document.querySelectorAll('.flow-node').length;
//     //     const connectionCount = this.jsPlumbInstance ? this.jsPlumbInstance.getAllConnections().length : 0;
        
//     //     if (this.nodeCountEl) this.nodeCountEl.textContent = nodeCount;
//     //     if (this.connectionCountEl) this.connectionCountEl.textContent = connectionCount;
//     // }

// //     async saveFlow() {
// //         const flowName = prompt('Enter flow name:');
// //         if (!flowName) return;

// //         try {
// //             const flowData = this.collectFlowData();
// //             console.log('📦 Collected flow data:', flowData);

// //             const payload = {
// //                 name: flowName,
// //                 config: flowData
// //             };

// //             const url = this.currentFlowId ? 
// //                 `/discount/whatssapAPI/api/flows/${this.currentFlowId}/update/` : 
// //                 `/discount/whatssapAPI/api/flows/create/`;

// //             const response = await this.apiPost(url, payload);
            
// //             if (response.success) {
// //                 this.showNotification('Flow saved successfully!', 'success');
// //                 this.currentFlowId = response.item.id;
// //                 this.loadFlows();
// //             } else {
// //                 throw new Error(response.error || 'Failed to save flow');
// //             }
            
// //         } catch (error) {
// //             console.error('Save error:', error);
// //             this.showNotification('Failed to save flow: ' + error.message, 'error');
// //         }
// //     }

// //     collectFlowData() {
// //         const nodes = Array.from(document.querySelectorAll('.flow-node')).map(node => {
// //             const nodeData = {
// //                 id: node.id,
// //                 type: node.dataset.nodeType || 'text-message',
// //                 position: {
// //                     x: parseInt(node.style.left) || 0,
// //                     y: parseInt(node.style.top) || 0
// //                 },
// //                 data: this.collectNodeData(node)
// //             };
// //             return nodeData;
// //         });

// //         const connections = this.jsPlumbInstance ? 
// //             this.jsPlumbInstance.getAllConnections().map(conn => ({
// //                 source: conn.sourceId,
// //                 target: conn.targetId,
// //                 data: {
// //                     branch: conn.getParameters()?.branch || null
// //                 }
// //             })) : [];

// //         return { 
// //             nodes, 
// //             connections,
// //             metadata: {
// //                 nodeCount: nodes.length,
// //                 connectionCount: connections.length,
// //                 savedAt: new Date().toISOString()
// //             }
// //         };
// //     }

// //     collectNodeData(node) {
// //         const nodeType = node.dataset.nodeType;
// //         const data = {};
        
// //         // جمع البيانات من جميع الحقول المدعومة
// //         const inputs = node.querySelectorAll('.node-input');
// //         inputs.forEach(input => {
// //             const fieldName = input.dataset.field;
// //             if (fieldName) {
// //                 if (input.type === 'file') {
// //                     // التعامل مع الملفات
// //                     if (input.files && input.files[0]) {
// //                         data[fieldName] = {
// //                             fileName: input.files[0].name,
// //                             fileType: input.files[0].type,
// //                             fileSize: input.files[0].size
// //                         };
// //                     }
// //                 } else if (input.type === 'checkbox' || input.type === 'radio') {
// //                     data[fieldName] = input.checked;
// //                 } else {
// //                     data[fieldName] = input.value;
// //                 }
// //             }
// //         });

// //         // جمع بيانات إضافية حسب نوع العقدة
// //         switch (nodeType) {
// //             case 'text-message':
// //                 data.content = node.querySelector('.message-content')?.value || '';
// //                 data.delay = parseInt(node.querySelector('.delay-value')?.value) || 0;
// //                 break;
// //             case 'media-message':
// //                 data.caption = node.querySelector('.caption-content')?.value || '';
// //                 data.mediaType = node.querySelector('.media-type-select')?.value || 'image';
// //                 data.delay = parseInt(node.querySelector('.delay-value')?.value) || 0;
// //                 break;
// //             case 'condition':
// //                 data.variable = node.querySelector('.condition-variable')?.value || '';
// //                 data.value = node.querySelector('.condition-value')?.value || '';
// //                 data.operator = node.querySelector('.condition-operator')?.value || 'equals';
// //                 break;
// //             case 'delay':
// //                 data.duration = parseInt(node.querySelector('.delay-duration')?.value) || 5;
// //                 break;
// //             case 'trigger':
// //                 data.triggerType = node.querySelector('.trigger-type')?.value || 'keyword';
// //                 data.keywords = node.querySelector('.trigger-keywords')?.value || '';
// //                 break;
// //         }

// //         return data;
// //     }

// //     async loadFlows() {
// //         try {
// //             const response = await this.apiGet('/discount/whatssapAPI/api/flows/');
// //             this.renderFlowSelect(response.items);
// //         } catch (error) {
// //             console.error('Failed to load flows:', error);
// //             this.showNotification('Failed to load flows list', 'error');
// //         }
// //     }

// //     renderFlowSelect(flows) {
// //         const select = this.flowSelect;
// //         if (!select) return;
        
// //         select.innerHTML = '<option value="">-- Select Flow --</option>';
        
// //         if (flows && flows.length > 0) {
// //             flows.forEach(flow => {
// //                 const option = document.createElement('option');
// //                 option.value = flow.id;
// //                 option.textContent = flow.name;
// //                 if (flow.id === this.currentFlowId) {
// //                     option.selected = true;
// //                 }
// //                 select.appendChild(option);
// //             });
// //         }
// //     }

// //     async loadFlow() {
// //         const flowId = this.flowSelect.value;
// //         if (!flowId) {
// //             this.showNotification('Please select a flow to load', 'error');
// //             return;
// //         }

// //         try {
// //             const response = await this.apiGet(`/discount/whatssapAPI/api/flows/${flowId}/`);
// //             this.renderFlow(response.item);
// //             this.currentFlowId = flowId;
// //             this.showNotification('Flow loaded successfully', 'success');
// //         } catch (error) {
// //             console.error('Load flow error:', error);
// //             this.showNotification('Failed to load flow: ' + error.message, 'error');
// //         }
// //     }

// //     renderFlow(flowData) {
// //         this.clearCanvas();
        
// //         if (!flowData.config) {
// //             this.showNotification('Invalid flow data', 'error');
// //             return;
// //         }
        
// //         const nodes = flowData.config.nodes || [];
// //         const connections = flowData.config.connections || [];
        
// //         console.log('📥 Rendering flow with nodes:', nodes);

// //         nodes.forEach(nodeData => {
// //             this.nodeCounter++;
// //             const nodeId = nodeData.id || `node-${this.nodeCounter}`;
            
// //             const node = document.createElement('div');
// //             node.className = 'flow-node';
// //             node.id = nodeId;
// //             node.style.left = (nodeData.position?.x || 100) + 'px';
// //             node.style.top = (nodeData.position?.y || 100) + 'px';
// //             node.dataset.nodeType = nodeData.type;
            
// //             const templateFunction = this.nodeTemplates[nodeData.type];
// //             if (templateFunction) {
// //                 node.innerHTML = templateFunction(nodeId);
// //             } else {
// //                 node.innerHTML = this.createTextMessageNode(nodeId);
// //             }
            
// //             this.flowCanvas.appendChild(node);
// //             this.initializeNode(nodeId);
            
// //             // تعبئة البيانات في العقدة
// //             this.populateNodeData(node, nodeData.data);
// //         });
        
// //         setTimeout(() => {
// //             if (this.jsPlumbInstance) {
// //                 connections.forEach(conn => {
// //                     this.createConnection(conn.source, conn.target, conn.data);
// //                 });
// //                 this.jsPlumbInstance.repaintEverything();
// //             }
// //         }, 500);
        
// //         this.updateStats();
// //     }

// //     populateNodeData(node, nodeData) {
// //         if (!nodeData) return;

// //         console.log('🔄 Populating node data:', nodeData);

// //         // تعبئة الحقول العامة
// //         Object.keys(nodeData).forEach(fieldName => {
// //             const input = node.querySelector(`[data-field="${fieldName}"]`);
// //             if (input) {
// //                 if (input.type === 'file') {
// //                     // لا يمكن تعيين قيمة لحقل ملف برمجياً
// //                     console.log('File field detected:', fieldName, nodeData[fieldName]);
// //                 } else if (input.type === 'checkbox' || input.type === 'radio') {
// //                     input.checked = Boolean(nodeData[fieldName]);
// //                 } else {
// //                     input.value = nodeData[fieldName] || '';
// //                 }
// //             }
// //         });

// //         // تعبئة بيانات محددة حسب نوع العقدة
// //         const nodeType = node.dataset.nodeType;
// //         switch (nodeType) {
// //             case 'text-message':
// //                 if (nodeData.content) {
// //                     const textarea = node.querySelector('.message-content');
// //                     if (textarea) textarea.value = nodeData.content;
// //                 }
// //                 if (nodeData.delay !== undefined) {
// //                     const delayInput = node.querySelector('.delay-value');
// //                     if (delayInput) delayInput.value = nodeData.delay;
// //                 }
// //                 break;
// //             case 'media-message':
// //                 if (nodeData.caption) {
// //                     const textarea = node.querySelector('.caption-content');
// //                     if (textarea) textarea.value = nodeData.caption;
// //                 }
// //                 if (nodeData.mediaType) {
// //                     const select = node.querySelector('.media-type-select');
// //                     if (select) select.value = nodeData.mediaType;
// //                 }
// //                 if (nodeData.delay !== undefined) {
// //                     const delayInput = node.querySelector('.delay-value');
// //                     if (delayInput) delayInput.value = nodeData.delay;
// //                 }
// //                 break;
// //             case 'condition':
// //                 if (nodeData.variable) {
// //                     const input = node.querySelector('.condition-variable');
// //                     if (input) input.value = nodeData.variable;
// //                 }
// //                 if (nodeData.value) {
// //                     const input = node.querySelector('.condition-value');
// //                     if (input) input.value = nodeData.value;
// //                 }
// //                 if (nodeData.operator) {
// //                     const select = node.querySelector('.condition-operator');
// //                     if (select) select.value = nodeData.operator;
// //                 }
// //                 break;
// //             case 'delay':
// //                 if (nodeData.duration !== undefined) {
// //                     const input = node.querySelector('.delay-duration');
// //                     if (input) input.value = nodeData.duration;
// //                 }
// //                 break;
// //             case 'trigger':
// //                 if (nodeData.triggerType) {
// //                     const select = node.querySelector('.trigger-type');
// //                     if (select) select.value = nodeData.triggerType;
// //                 }
// //                 if (nodeData.keywords) {
// //                     const input = node.querySelector('.trigger-keywords');
// //                     if (input) input.value = nodeData.keywords;
// //                 }
// //                 break;
// //         }
// //     }

// //     addSampleFlow() {
// //         const triggerId = this.createNode('trigger', 100, 100);
// //         const textId = this.createNode('text-message', 400, 100);
// //         const conditionId = this.createNode('condition', 400, 300);
// //         const mediaId = this.createNode('media-message', 700, 300);
        
// //         setTimeout(() => {
// //             this.createConnection(triggerId, textId);
// //             this.createConnection(textId, conditionId);
// //             this.createConnection(conditionId, mediaId, { branch: 'true' });
// //         }, 100);
// //     }

// //     async apiGet(url) {
// //         const response = await fetch(url, {
// //             headers: { 
// //                 'Accept': 'application/json',
// //                 'X-CSRFToken': this.csrfToken
// //             }
// //         });
// //         if (!response.ok) throw new Error(`HTTP ${response.status}`);
// //         return response.json();
// //     }

// //     async apiPost(url, data) {
// //         const response = await fetch(url, {
// //             method: 'POST',
// //             headers: {
// //                 'Content-Type': 'application/json',
// //                 'X-CSRFToken': this.csrfToken
// //             },
// //             body: JSON.stringify(data)
// //         });

// //         if (!response.ok) {
// //             const errorText = await response.text();
// //             throw new Error(`HTTP ${response.status}: ${errorText}`);
// //         }
// //         return response.json();
// //     }

// //     showNotification(message, type = 'info') {
// //         const notification = document.createElement('div');
// //         notification.style.cssText = `
// //             position: fixed;
// //             top: 20px;
// //             right: 20px;
// //             padding: 12px 20px;
// //             border-radius: 8px;
// //             color: white;
// //             font-weight: 500;
// //             z-index: 10000;
// //             transition: all 0.3s ease;
// //             background: ${type === 'success' ? '#10B981' : type === 'error' ? '#EF4444' : '#3B82F6'};
// //             box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
// //         `;
// //         notification.textContent = message;
// //         document.body.appendChild(notification);

// //         setTimeout(() => {
// //             notification.style.opacity = '0';
// //             setTimeout(() => notification.remove(), 300);
// //         }, 3000);
// //     }

// //     addVariable() {
// //         const variableName = prompt('Enter variable name:');
// //         if (!variableName) return;
// //         const variableValue = prompt('Enter variable value:');
// //         this.showNotification(`Variable added: ${variableName}`, 'success');
// //     }

// //     clearCanvas() {
// //         if (confirm('Are you sure you want to clear the canvas? All nodes and connections will be lost.')) {
// //             document.querySelectorAll('.flow-node').forEach(node => {
// //                 if (this.jsPlumbInstance) {
// //                     this.jsPlumbInstance.removeAllEndpoints(node.id);
// //                 }
// //                 node.remove();
// //             });
            
// //             this.nodeCounter = 0;
// //             this.currentFlowId = null;
// //             this.updateStats();
// //             this.showNotification('Canvas cleared successfully', 'success');
// //         }
// //     }

// //     autoLayout() {
// //         const nodes = document.querySelectorAll('.flow-node');
// //         if (nodes.length === 0) {
// //             this.showNotification('No nodes to arrange', 'warning');
// //             return;
// //         }
        
// //         const canvasWidth = this.flowCanvas.clientWidth;
// //         const nodeWidth = 280;
// //         const horizontalSpacing = 100;
// //         const verticalSpacing = 120;
        
// //         let x = 100;
// //         let y = 100;
// //         let rowHeight = 0;
        
// //         nodes.forEach((node, index) => {
// //             node.style.left = x + 'px';
// //             node.style.top = y + 'px';
            
// //             const nodeHeight = node.offsetHeight;
// //             rowHeight = Math.max(rowHeight, nodeHeight);
            
// //             x += nodeWidth + horizontalSpacing;
            
// //             if (x + nodeWidth > canvasWidth - 100) {
// //                 x = 100;
// //                 y += rowHeight + verticalSpacing;
// //                 rowHeight = 0;
// //             }
            
// //             if (this.jsPlumbInstance) {
// //                 this.jsPlumbInstance.revalidate(node.id);
// //             }
// //         });
        
// //         if (this.jsPlumbInstance) {
// //             this.jsPlumbInstance.repaintEverything();
// //         }
// //         this.showNotification('Nodes auto-arranged successfully', 'success');
// //     }

// //     removeNode(nodeId) {
// //         if (confirm('Are you sure you want to delete this node?')) {
// //             if (this.jsPlumbInstance) {
// //                 this.jsPlumbInstance.removeAllEndpoints(nodeId);
// //                 this.jsPlumbInstance.deleteConnectionsForElement(nodeId);
// //             }
            
// //             document.getElementById(nodeId)?.remove();
            
// //             if (this.selectedNode && this.selectedNode.id === nodeId) {
// //                 this.selectedNode = null;
// //             }
            
// //             this.updateStats();
// //             this.showNotification('Node deleted', 'success');
// //         }
// //     }

// //     connectNode(nodeId, branch = null) {
// //         if (this.connectionMode && this.connectionSource === nodeId) {
// //             this.cancelConnectionMode();
// //         } else {
// //             this.enableConnectionMode(nodeId, branch);
// //         }
// //     }

// //     enableConnectionMode(sourceNodeId, branch = null) {
// //         this.connectionMode = true;
// //         this.connectionSource = sourceNodeId;
// //         this.connectionBranch = branch;
        
// //         const sourceNode = document.getElementById(sourceNodeId);
// //         if (sourceNode) {
// //             sourceNode.style.boxShadow = '0 0 0 3px #10b981';
// //             sourceNode.classList.add('connection-source');
// //         }
        
// //         document.body.style.cursor = 'crosshair';
// //         this.showNotification('Click on target node to connect. Press ESC to cancel.', 'info');
        
// //         this.escapeHandler = (e) => {
// //             if (e.key === 'Escape') {
// //                 this.cancelConnectionMode();
// //             }
// //         };
// //         document.addEventListener('keydown', this.escapeHandler);
        
// //         this.connectionClickHandler = (e) => this.handleConnectionTarget(e);
// //         this.flowCanvas.addEventListener('click', this.connectionClickHandler);
// //     }

// //     cancelConnectionMode() {
// //         this.connectionMode = false;
// //         if (this.connectionSource) {
// //             const sourceNode = document.getElementById(this.connectionSource);
// //             if (sourceNode) {
// //                 sourceNode.style.boxShadow = '';
// //                 sourceNode.classList.remove('connection-source');
// //             }
// //         }
// //         this.connectionSource = null;
// //         this.connectionBranch = null;
// //         document.body.style.cursor = '';
        
// //         if (this.escapeHandler) {
// //             document.removeEventListener('keydown', this.escapeHandler);
// //         }
// //         if (this.connectionClickHandler) {
// //             this.flowCanvas.removeEventListener('click', this.connectionClickHandler);
// //         }
        
// //         this.showNotification('Connection mode cancelled', 'info');
// //     }

// //     handleConnectionTarget(e) {
// //         if (!this.connectionMode) return;
        
// //         const targetNode = e.target.closest('.flow-node');
// //         if (!targetNode) return;
        
// //         const targetNodeId = targetNode.id;
        
// //         if (targetNodeId === this.connectionSource) {
// //             this.showNotification('Cannot connect to the same node', 'error');
// //             return;
// //         }
        
// //         this.createConnection(this.connectionSource, targetNodeId, { branch: this.connectionBranch });
// //         this.cancelConnectionMode();
// //     }

// //     createConnection(sourceId, targetId, connectionData = {}) {
// //         if (!this.jsPlumbInstance) return;
        
// //         try {
// //             const existingConnections = this.jsPlumbInstance.getConnections({
// //                 source: sourceId,
// //                 target: targetId
// //             });
            
// //             existingConnections.forEach(conn => {
// //                 this.jsPlumbInstance.deleteConnection(conn);
// //             });
            
// //             const connection = this.jsPlumbInstance.connect({
// //                 source: sourceId,
// //                 target: targetId,
// //                 anchors: ["Right", "Left"],
// //                 connector: ["Flowchart", { cornerRadius: 5 }],
// //                 paintStyle: { 
// //                     stroke: "#7C3AED", 
// //                     strokeWidth: 2
// //                 },
// //                 hoverPaintStyle: { stroke: "#10B981", strokeWidth: 3 },
// //                 overlays: [
// //                     ["Arrow", { 
// //                         location: 1, 
// //                         width: 12, 
// //                         height: 12,
// //                         foldback: 0.8 
// //                     }]
// //                 ],
// //                 parameters: connectionData
// //             });
            
// //             this.showNotification(`Connected ${sourceId} to ${targetId}`, 'success');
            
// //         } catch (error) {
// //             console.error('Failed to create connection:', error);
// //             this.showNotification('Failed to create connection', 'error');
// //         }
// //     }

// //     selectNode(nodeId) {
// //         if (this.selectedNode) {
// //             this.selectedNode.classList.remove('selected');
// //         }
        
// //         this.selectedNode = document.getElementById(nodeId);
// //         if (this.selectedNode) {
// //             this.selectedNode.classList.add('selected');
// //         }
// //     }

// //     saveNodePositions() {
// //         // يمكن استخدام هذه الدالة لحفظ المواقع تلقائياً إذا لزم الأمر
// //     }
// // }









































// {% load static %}
 
//     <!-- Fonts -->
//     <link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@300;400;500;700;800&display=swap" rel="stylesheet">
    
//     <style>
//         :root {
//             --primary: #7C3AED;
//             --primary-dark: #6D28D9;
//             --secondary: #10B981;
//             --danger: #EF4444;
//             --warning: #F59E0B;
//             --info: #3B82F6;
//             --background: #0F172A;
//             --surface: #1E293B;
//             --surface-light: #334155;
//             --surface-dark: #0F172A;
//             --text-primary: #F8FAFC;
//             --text-secondary: #CBD5E1;
//             --text-muted: #64748B;
//             --border: #334155;
//             --radius: 12px;
//             --shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
//             --sidebar-width: 320px;
//             --header-height: 60px;
//         }

//         * {
//             margin: 0;
//             padding: 0;
//             box-sizing: border-box;
//         }

//         body {
//             font-family: 'Tajawal', sans-serif;
//             background: var(--background);
//             color: var(--text-primary);
//             line-height: 1.6;
//             direction: ltr;
//         }

//         .none {
//             display: none !important;
//         }

//         /* Container for automations list */
//         .containerNew_auto {
//             max-width: 100%;
//             margin: 0 auto;
//             padding: 2rem;
//         }

//         .containerNew_auto .header {
//             display: flex;
//             justify-content: space-between;
//             align-items: flex-start;
//             margin-bottom: 2rem;
//             background-color: transparent;
//             height: auto;
//             padding: 0;
//         }

//         .containerNew_auto .title-section h1 {
//             font-size: 2rem;
//             font-weight: 700;
//             margin-bottom: 0.5rem;
//         }

//         .containerNew_auto .title-section p {
//             color: var(--text-secondary);
//             font-size: 1rem;
//         }

//         /* Buttons */
//         .btn {
//             display: inline-flex;
//             align-items: center;
//             gap: 0.5rem;
//             padding: 0.75rem 1.5rem;
//             border: none;
//             border-radius: 8px;
//             font-family: inherit;
//             font-size: 0.875rem;
//             font-weight: 500;
//             cursor: pointer;
//             transition: all 0.2s ease;
//             text-decoration: none;
//         }

//         .btn-primary {
//             background: linear-gradient(135deg, var(--primary), var(--primary-dark));
//             color: white;
//         }

//         .btn-primary:hover:not(:disabled) {
//             transform: translateY(-1px);
//             box-shadow: 0 5px 15px rgba(124, 58, 237, 0.4);
//         }

//         .btn-secondary {
//             background: var(--surface-light);
//             color: var(--text-primary);
//             border: 1px solid var(--border);
//         }

//         .btn-secondary:hover:not(:disabled) {
//             background: var(--surface);
//             border-color: var(--primary);
//         }

//         .btn-danger {
//             background: var(--danger);
//             color: white;
//         }

//         .btn-sm {
//             padding: 0.5rem 0.875rem;
//             font-size: 0.75rem;
//         }

//         .btn-icon {
//             padding: 0.5rem;
//             width: 32px;
//             height: 32px;
//             display: flex;
//             align-items: center;
//             justify-content: center;
//         }

//         /* Search */
//         .search-box {
//             margin-bottom: 2rem;
//         }

//         .search-input {
//             width: 100%;
//             padding: 0.75rem 1rem;
//             background: var(--surface);
//             border: 1px solid var(--border);
//             border-radius: 8px;
//             color: var(--text-primary);
//             font-family: inherit;
//             font-size: 0.875rem;
//         }

//         .search-input:focus {
//             outline: none;
//             border-color: var(--primary);
//         }

//         /* Table */
//         .automations-table {
//             background: var(--surface);
//             border-radius: 12px;
//             overflow: hidden;
//             box-shadow: var(--shadow);
//         }

//         .table-header {
//             display: grid;
//             grid-template-columns: 2fr 1fr 1fr 2fr 1fr;
//             gap: 1rem;
//             padding: 1rem 1.5rem;
//             background: var(--surface-light);
//             border-bottom: 1px solid var(--border);
//             font-weight: 600;
//             color: var(--text-secondary);
//         }

//         .table-row {
//             display: grid;
//             grid-template-columns: 2fr 1fr 1fr 2fr 1fr;
//             gap: 1rem;
//             padding: 1rem 1.5rem;
//             border-bottom: 1px solid var(--border);
//             align-items: center;
//         }

//         .table-row:last-child {
//             border-bottom: none;
//         }

//         .table-row:hover {
//             background: var(--surface-light);
//         }

//         /* Status Badges */
//         .status-active {
//             background: var(--secondary);
//             color: white;
//             padding: 0.25rem 0.75rem;
//             border-radius: 20px;
//             font-size: 0.75rem;
//             font-weight: 600;
//         }

//         .status-inactive {
//             background: var(--text-muted);
//             color: white;
//             padding: 0.25rem 0.75rem;
//             border-radius: 20px;
//             font-size: 0.75rem;
//             font-weight: 600;
//         }

//         /* Actions */
//         .actions {
//             display: flex;
//             gap: 0.5rem;
//         }

//         .menu-button {
//             position: relative;
//         }

//         .menu-dropdown {
//             position: absolute;
//             top: 100%;
//             right: 0;
//             background: var(--surface);
//             border: 1px solid var(--border);
//             border-radius: 8px;
//             padding: 0.5rem;
//             min-width: 120px;
//             box-shadow: var(--shadow);
//             z-index: 100;
//             display: none;
//         }

//         .menu-dropdown.show {
//             display: block;
//         }

//         .menu-item {
//             display: block;
//             width: 100%;
//             padding: 0.5rem;
//             background: none;
//             border: none;
//             color: var(--text-primary);
//             text-align: right;
//             cursor: pointer;
//             border-radius: 4px;
//             font-family: inherit;
//         }

//         .menu-item:hover {
//             background: var(--surface-light);
//         }

//         /* Empty State */
//         .empty-state {
//             text-align: center;
//             padding: 3rem;
//             color: var(--text-secondary);
//         }

//         .empty-state .icon {
//             font-size: 4rem;
//             margin-bottom: 1rem;
//             opacity: 0.5;
//         }

//         /* Utility Classes */
//         .text-center {
//             text-align: center;
//         }

//         .text-muted {
//             color: var(--text-muted);
//         }

//         /* Flow Builder Styles */
//         .app-container {
//             display: none;
//             flex-direction: row;
//             height: 75vh;
//         }

//         .flow-builder-active {
//             display: flex !important;
//         }

//         /* Sidebar */
//         .sidebar {
//             width: var(--sidebar-width);
//             background: var(--surface-dark);
//             border-left: 1px solid var(--border);
//             display: flex;
//             flex-direction: column;
//             height: 100%;
//             overflow: auto;
//         }

//         .sidebar-section {
//             padding: 1.5rem;
//             border-bottom: 1px solid var(--border);
//         }

//         .section-title {
//             font-size: 0.875rem;
//             font-weight: 700;
//             color: var(--text-secondary);
//             margin-bottom: 1rem;
//             text-transform: uppercase;
//             letter-spacing: 0.5px;
//             display: flex;
//             align-items: center;
//             gap: 0.5rem;
//         }

//         .section-title .icon {
//             font-size: 1rem;
//         }

//         /* Components Grid */
//         .components-grid {
//             display: grid;
//             gap: 0.75rem;
//         }

//         .component-item {
//             background: var(--surface);
//             border: 1px solid var(--border);
//             border-radius: 8px;
//             padding: 1rem;
//             cursor: grab;
//             transition: all 0.2s ease;
//             text-align: right;
//             user-select: none;
//         }

//         .component-item:hover {
//             border-color: var(--primary);
//             transform: translateY(-2px);
//         }

//         .component-header {
//             display: flex;
//             align-items: center;
//             gap: 0.5rem;
//             margin-bottom: 0.5rem;
//         }

//         .component-icon {
//             width: 24px;
//             height: 24px;
//             background: var(--primary);
//             border-radius: 6px;
//             display: flex;
//             align-items: center;
//             justify-content: center;
//             font-size: 0.75rem;
//         }

//         .component-title {
//             font-weight: 600;
//             font-size: 0.875rem;
//         }

//         .component-desc {
//             font-size: 0.75rem;
//             color: var(--text-muted);
//             line-height: 1.4;
//         }

//         /* Main Content */
//         .main-content {
//             flex: 1;
//             display: flex;
//             flex-direction: column;
//             background: var(--background);
//         }

//         /* Header */
//         .header {
//             height: var(--header-height);
//             background: var(--surface);
//             border-bottom: 1px solid var(--border);
//             padding: 0 1.5rem;
//             display: flex;
//             align-items: center;
//             justify-content: space-between;
//         }

//         .header-title {
//             font-size: 1.25rem;
//             font-weight: 700;
//         }

//         .header-actions {
//             display: flex;
//             gap: 0.75rem;
//             align-items: center;
//         }

//         /* Canvas Area */
//         .canvas-area {
//             flex: 1;
//             background: 
//                 radial-gradient(circle at 20% 80%, rgba(124, 58, 237, 0.1) 0%, transparent 50%),
//                 radial-gradient(circle at 80% 20%, rgba(16, 185, 129, 0.1) 0%, transparent 50%),
//                 var(--background);
//             position: relative;
//             overflow: auto;
//         }

//         #flow-canvas {
//             width: 100%;
//             height: 100%;
//             min-height: 800px;
//             position: relative;
//             background-image: 
//                 linear-gradient(rgba(255, 255, 255, 0.03) 1px, transparent 1px),
//                 linear-gradient(90deg, rgba(255, 255, 255, 0.03) 1px, transparent 1px);
//             background-size: 50px 50px;
//         }

//         /* Flow Node Styles */
//         .flow-node {
//             position: absolute;
//             width: 280px;
//             background: var(--surface);
//             border: 2px solid var(--border);
//             border-radius: 12px;
//             box-shadow: var(--shadow);
//             transition: all 0.3s ease;
//             cursor: move;
//             z-index: 100;
//         }

//         .flow-node:hover {
//             border-color: var(--primary);
//             transform: translateY(-2px);
//         }

//         .flow-node.selected {
//             border-color: var(--primary);
//             box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.2);
//         }

//         .node-header {
//             background: linear-gradient(135deg, var(--primary), var(--primary-dark));
//             padding: 1rem;
//             border-radius: 10px 10px 0 0;
//             display: flex;
//             align-items: center;
//             gap: 0.75rem;
//             color: white;
//         }

//         .node-icon {
//             width: 32px;
//             height: 32px;
//             background: rgba(255, 255, 255, 0.2);
//             border-radius: 8px;
//             display: flex;
//             align-items: center;
//             justify-content: center;
//             font-size: 1rem;
//         }

//         .node-title {
//             flex: 1;
//             font-weight: 700;
//             font-size: 0.875rem;
//         }

//         .node-type {
//             font-size: 0.75rem;
//             opacity: 0.9;
//             background: rgba(255, 255, 255, 0.2);
//             padding: 0.25rem 0.5rem;
//             border-radius: 4px;
//         }

//         .node-body {
//             padding: 1rem;
//         }

//         .node-content {
//             font-size: 0.875rem;
//             color: var(--text-secondary);
//             margin-bottom: 1rem;
//         }

//         .node-properties {
//             display: flex;
//             flex-direction: column;
//             gap: 0.5rem;
//         }

//         .node-property {
//             display: flex;
//             justify-content: space-between;
//             align-items: center;
//             font-size: 0.75rem;
//             padding: 0.5rem;
//             background: var(--surface-light);
//             border-radius: 6px;
//         }

//         .node-footer {
//             padding: 1rem;
//             border-top: 1px solid var(--border);
//             display: flex;
//             gap: 0.5rem;
//             background: rgba(255, 255, 255, 0.02);
//         }

//         /* Overview Stats */
//         .overview-stats {
//             display: grid;
//             grid-template-columns: 1fr 1fr;
//             gap: 0.75rem;
//             margin-bottom: 1rem;
//         }

//         .stat-item {
//             background: var(--surface);
//             border: 1px solid var(--border);
//             border-radius: 8px;
//             padding: 0.75rem;
//             text-align: center;
//         }

//         .stat-value {
//             font-size: 1.25rem;
//             font-weight: 700;
//             color: var(--primary);
//             margin-bottom: 0.25rem;
//         }

//         .stat-label {
//             font-size: 0.75rem;
//             color: var(--text-muted);
//         }

//         /* Form Elements */
//         .form-group {
//             margin-bottom: 1rem;
//         }

//         .form-label {
//             display: block;
//             font-size: 0.875rem;
//             font-weight: 500;
//             margin-bottom: 0.5rem;
//             color: var(--text-primary);
//         }

//         .form-input, .form-select, .form-textarea {
//             width: 100%;
//             padding: 0.75rem;
//             background: var(--surface-light);
//             border: 1px solid var(--border);
//             border-radius: 8px;
//             color: var(--text-primary);
//             font-family: inherit;
//             font-size: 0.875rem;
//             transition: all 0.2s ease;
//         }

//         .form-input:focus, .form-select:focus, .form-textarea:focus {
//             outline: none;
//             border-color: var(--primary);
//             box-shadow: 0 0 0 3px rgba(124, 58, 237, 0.2);
//         }

//         /* Scrollbar */
//         ::-webkit-scrollbar {
//             width: 6px;
//         }

//         ::-webkit-scrollbar-track {
//             background: var(--surface-light);
//         }

//         ::-webkit-scrollbar-thumb {
//             background: var(--border);
//             border-radius: 3px;
//         }

//         ::-webkit-scrollbar-thumb:hover {
//             background: var(--text-muted);
//         }

//         /* Connection Styles */
//         .jtk-connector {
//             cursor: pointer;
//             z-index: 10;
//         }

//         .jtk-endpoint {
//             cursor: pointer;
//             z-index: 11;
//         }

//         .jtk-overlay {
//             cursor: pointer;
//             z-index: 12;
//         }

//         /* تأثيرات للعقدة في وضع الربط */
//         .flow-node.connection-source {
//             animation: pulse 2s infinite;
//         }

//         @keyframes pulse {
//             0% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
//             70% { box-shadow: 0 0 0 10px rgba(16, 185, 129, 0); }
//             100% { box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
//         }

//         /* تحسين مظهر الأزرار */
//         .btn-group {
//             display: flex;
//             gap: 0.75rem;
//         }

//         .w-full {
//             width: 100%;
//         }

//         /* أنماط عناصر التحكم في التكبير */
//         .zoom-controls {
//             display: flex;
//             align-items: center;
//             gap: 0.5rem;
//             background: var(--surface);
//             border: 1px solid var(--border);
//             border-radius: 8px;
//             padding: 0.5rem;
//         }

//         .zoom-buttons {
//             display: flex;
//             align-items: center;
//             gap: 0.25rem;
//         }

//         .zoom-level {
//             font-size: 0.75rem;
//             font-weight: 600;
//             color: var(--text-primary);
//             min-width: 45px;
//             text-align: center;
//         }

//         /* أنماط الـ Trigger المتقدم */
//         .trigger-node {
//             width: 320px;
//         }

//         .trigger-conditions {
//             max-height: 200px;
//             overflow-y: auto;
//             margin-bottom: 1rem;
//             border: 1px solid var(--border);
//             border-radius: 8px;
//             padding: 0.75rem;
//         }

//         .condition-item {
//             background: var(--surface-light);
//             border-radius: 6px;
//             padding: 0.75rem;
//             margin-bottom: 0.5rem;
//             border-left: 3px solid var(--primary);
//         }

//         .condition-header {
//             display: flex;
//             justify-content: space-between;
//             align-items: center;
//             margin-bottom: 0.5rem;
//             font-size: 0.875rem;
//             font-weight: 600;
//         }

//         .trigger-actions {
//             border-top: 1px solid var(--border);
//             padding-top: 1rem;
//         }

//         .action-item {
//             display: flex;
//             justify-content: space-between;
//             align-items: center;
//             padding: 0.5rem;
//             background: var(--surface-light);
//             border-radius: 6px;
//         }

//         /* أنماط الـ Modal */
//         .modal-overlay {
//             position: fixed;
//             top: 0;
//             left: 0;
//             right: 0;
//             bottom: 0;
//             background: rgba(0, 0, 0, 0.5);
//             display: flex;
//             align-items: center;
//             justify-content: center;
//             z-index: 10000;
//         }

//         .modal-content {
//             background: var(--surface);
//             border-radius: 12px;
//             width: 90%;
//             max-width: 500px;
//             max-height: 80vh;
//             overflow: auto;
//         }

//         .modal-header {
//             padding: 1.5rem;
//             border-bottom: 1px solid var(--border);
//             display: flex;
//             justify-content: space-between;
//             align-items: center;
//         }

//         .modal-body {
//             padding: 1.5rem;
//         }

//         .modal-footer {
//             padding: 1.5rem;
//             border-top: 1px solid var(--border);
//             display: flex;
//             gap: 0.75rem;
//             justify-content: flex-end;
//         }

//         /* أنماط الوسوم */
//         .tags-list {
//             display: flex;
//             flex-wrap: wrap;
//             gap: 0.5rem;
//             margin-bottom: 1rem;
//         }

//         .tag-item {
//             display: flex;
//             align-items: center;
//             gap: 0.5rem;
//             padding: 0.5rem;
//             background: var(--surface-light);
//             border: 1px solid var(--border);
//             border-radius: 6px;
//             cursor: pointer;
//             transition: all 0.2s ease;
//         }

//         .tag-item:hover {
//             border-color: var(--primary);
//         }

//         .tag-item.selected {
//             background: var(--primary);
//             color: white;
//         }

//         .tag-color {
//             width: 12px;
//             height: 12px;
//             border-radius: 50%;
//         }

//         .tag-name {
//             font-size: 0.875rem;
//         }

//         .tag-badge {
//             display: inline-flex;
//             align-items: center;
//             padding: 0.25rem 0.5rem;
//             background: var(--primary);
//             color: white;
//             border-radius: 4px;
//             font-size: 0.75rem;
//             margin: 0.125rem;
//         }

//         .tag-selector {
//             display: flex;
//             gap: 0.5rem;
//             align-items: center;
//         }

//         .add-tag-section {
//             border-top: 1px solid var(--border);
//             padding-top: 1rem;
//             margin-top: 1rem;
//         }

//         .add-tag-section .form-group {
//             display: flex;
//             gap: 0.5rem;
//             align-items: center;
//         }

//         .add-tag-section input[type="text"] {
//             flex: 1;
//         }

//         .add-tag-section input[type="color"] {
//             width: 40px;
//             height: 40px;
//             padding: 0;
//             border: none;
//             background: transparent;
//         }

//         .mt-1 {
//             margin-top: 0.25rem;
//         }
//     </style>
 
//     <!-- Automations List -->
//     <div class="containerNew_auto" id="automations-container">
//         <!-- Header -->
//         <div class="header">
//             <div class="title-section">
//                 <h1>My Automations</h1>
//                 <p>Respond automatically to messages based on your own criteria</p>
//             </div>
//             <button class="btn btn-primary" id="new-automation-btn">
//                 <span>+</span>
//                 New Automation
//             </button>
//         </div>

//         <!-- Search -->
//         <div class="search-box">
//             <input type="text" class="search-input" placeholder="Search by name or trigger text" id="search-input">
//         </div>

//         <!-- Automations Table -->
//         <div class="automations-table">
//             <div class="table-header">
//                 <div>Name</div>
//                 <div class="text-center">Runs</div>
//                 <div class="text-center">Status</div>
//                 <div>Last Updated</div>
//                 <div class="text-center">Actions</div>
//             </div>
//             <div id="automations-list" style="overflow: auto; max-height: 60vh;">
//                 <!-- سيتم ملؤها بالبيانات -->
//             </div>
//         </div>
//     </div>

//     <!-- Flow Builder -->
//     <div class="app-container none" id="flow-builder-container">

         


//         <!-- Main Content -->
//         <main class="main-content">
//             <!-- Header -->
//             <header class="header"> 
//                 <div class="header-title">
//                 <button class="btn btn-primary" id="back_to_auto">
//                 <span> </span>
//                 Back
//             </button>
//             <script>
//                 document.getElementById('back_to_auto').addEventListener('click', function() {
//                     document.getElementById('flow-builder-container').classList.add('none');
//                      document.getElementById('flow-builder-container').classList.remove('flow-builder-active');

                     
//                     document.getElementById('automations-container').classList.remove('none');
//                 });
//             </script>
//         </div>
//                 <div class="header-actions">
//                     <select class="form-select" id="flow-select" style="width: 200px;">
//                         <option value="">-- Select Flow --</option>
//                     </select>
//                     <button class="btn btn-secondary" id="load-flow-btn">Load</button>
//                     <button class="btn btn-primary" id="save-flow-btn">Save</button>
//                     <button class="btn btn-secondary" id="layout-btn">Auto Layout</button>
//                     <button class="btn btn-danger" id="clear-btn">Clear All</button>
//                 </div>
//             </header>

//             <!-- Canvas Area -->
//             <div class="canvas-area">
//                 <div id="flow-canvas">
//                     <div class="empty-state">
//                         <div class="icon">🎨</div>
//                         <h3>Welcome to Flow Builder</h3>
//                         <p>Drag components from the sidebar to start building your workflow</p>
//                         <div class="btn-group">
//                             <button class="btn btn-primary" id="sample-flow-btn">
//                                 Create Sample Flow
//                             </button>
//                             <button class="btn btn-secondary" id="load-existing-btn">
//                                 Load Existing Flow
//                             </button>
//                         </div>
//                     </div>
//                 </div>
//             </div>

//         </main>

//         <!-- Sidebar -->
//         <aside class="sidebar">
//             <!-- Overview Section -->
//             <div class="sidebar-section">
//                 <h3 class="section-title">
//                     <span class="icon">📊</span>
//                     Overview
//                 </h3>
//                 <div class="overview-stats">
//                     <div class="stat-item">
//                         <div class="stat-value" id="node-count">0</div>
//                         <div class="stat-label">Nodes</div>
//                     </div>
//                     <div class="stat-item">
//                         <div class="stat-value" id="connection-count">0</div>
//                         <div class="stat-label">Connections</div>
//                     </div>
//                 </div>
//                 <button class="btn btn-primary w-full" id="add-variable-btn">
//                     <span>+</span>
//                     Add Variable
//                 </button>
//             </div>

//             <!-- Messages Section -->
//             <div class="sidebar-section">
//                 <h3 class="section-title">
//                     <span class="icon">💬</span>
//                     Messages
//                 </h3>
//                 <div class="components-grid">
//                     <div class="component-item" data-type="text-message" draggable="true">
//                         <div class="component-header">
//                             <div class="component-icon">📝</div>
//                             <div class="component-title">Text Message</div>
//                         </div>
//                         <div class="component-desc">Send a simple text message</div>
//                     </div>
//                     <div class="component-item" data-type="media-message" draggable="true">
//                         <div class="component-header">
//                             <div class="component-icon">🖼️</div>
//                             <div class="component-title">Media</div>
//                         </div>
//                         <div class="component-desc">Image, Video, Audio, File</div>
//                     </div>
//                     <div class="component-item" data-type="buttons-message" draggable="true">
//                         <div class="component-header">
//                             <div class="component-icon">🔘</div>
//                             <div class="component-title">Interactive Buttons</div>
//                         </div>
//                         <div class="component-desc">Button choices</div>
//                     </div>
//                     <div class="component-item" data-type="list-message" draggable="true">
//                         <div class="component-header">
//                             <div class="component-icon">📋</div>
//                             <div class="component-title">Interactive List</div>
//                         </div>
//                         <div class="component-desc">Dropdown list for selections</div>
//                     </div>
//                 </div>
//             </div>

//             <!-- Actions Section -->
//             <div class="sidebar-section">
//                 <h3 class="section-title">
//                     <span class="icon">⚡</span>
//                     Actions
//                 </h3>
//                 <div class="components-grid">
//                     <div class="component-item" data-type="condition" draggable="true">
//                         <div class="component-header">
//                             <div class="component-icon">🔀</div>
//                             <div class="component-title">Condition</div>
//                         </div>
//                         <div class="component-desc">Branch based on a condition</div>
//                     </div>
//                     <div class="component-item" data-type="trigger" draggable="true">
//                         <div class="component-header">
//                             <div class="component-icon">🔔</div>
//                             <div class="component-title">Flow Trigger</div>
//                         </div>
//                         <div class="component-desc">Start flow when conditions are met</div>
//                     </div>
//                     <div class="component-item" data-type="delay" draggable="true">
//                         <div class="component-header">
//                             <div class="component-icon">⏱️</div>
//                             <div class="component-title">Delay</div>
//                         </div>
//                         <div class="component-desc">Delay before the next action</div>
//                     </div>
//                     <div class="component-item" data-type="webhook" draggable="true">
//                         <div class="component-header">
//                             <div class="component-icon">🌐</div>
//                             <div class="component-title">Webhook</div>
//                         </div>
//                         <div class="component-desc">Call external API</div>
//                     </div>
//                 </div>
//             </div>

//             <!-- Contact Management -->
//             <div class="sidebar-section">
//                 <h3 class="section-title">
//                     <span class="icon">👥</span>
//                     Contact Management
//                 </h3>
//                 <div class="components-grid">
//                     <div class="component-item" data-type="add-contact" draggable="true">
//                         <div class="component-header">
//                             <div class="component-icon">➕</div>
//                             <div class="component-title">Add Contact</div>
//                         </div>
//                         <div class="component-desc">Add a contact to the group</div>
//                     </div>
//                     <div class="component-item" data-type="update-contact" draggable="true">
//                         <div class="component-header">
//                             <div class="component-icon">✏️</div>
//                             <div class="component-title">Update Contact</div>
//                         </div>
//                         <div class="component-desc">Update contact information</div>
//                     </div>
//                 </div>
//             </div>

//             <!-- Tags Section -->
//             <div class="sidebar-section">
//                 <h3 class="section-title">
//                     <span class="icon">🏷️</span>
//                     Tags
//                 </h3>
//                 <div class="components-grid">
//                     <div class="component-item" data-type="add-tags" draggable="true">
//                         <div class="component-header">
//                             <div class="component-icon">➕</div>
//                             <div class="component-title">Add Tags</div>
//                         </div>
//                         <div class="component-desc">Add tags to contacts</div>
//                     </div>
//                     <div class="component-item" data-type="remove-tags" draggable="true">
//                         <div class="component-header">
//                             <div class="component-icon">➖</div>
//                             <div class="component-title">Remove Tags</div>
//                         </div>
//                         <div class="component-desc">Remove tags from contacts</div>
//                     </div>
//                 </div>
//             </div>
//         </aside>
//     </div>

//     <script src="https://cdnjs.cloudflare.com/ajax/libs/jsPlumb/2.15.6/js/jsplumb.min.js"></script>
  
  
//   <script>
//     // دالة عالمية للحصول على قيمة الكوكي
//     function getCookie(name) {
//         let cookieValue = null;
//         if (document.cookie && document.cookie !== '') {
//             const cookies = document.cookie.split(';');
//             for (let i = 0; i < cookies.length; i++) {
//                 const cookie = cookies[i].trim();
//                 if (cookie.substring(0, name.length + 1) === (name + '=')) {
//                     cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
//                     break;
//                 }
//             }
//         }
//         return cookieValue;
//     }

//     /**
//      * كلاس لإدارة قائمة التلقائيات
//      */
//     class AutomationsList {
//         constructor() {
//             this.apiBaseUrl = '/discount/whatssapAPI';
//             this.flows = [];
//             this.selectedFlowId = null;
//             this.initializeEventListeners();
//             this.loadAutomations();
//         }

//         /**
//          * تهيئة مستمعي الأحداث
//          */
//         initializeEventListeners() {
//             document.getElementById('new-automation-btn').addEventListener('click', () => {
//                 this.showCreateFlowForm();
//             });

//             document.getElementById('search-input').addEventListener('input', (e) => {
//                 this.searchAutomations(e.target.value);
//             });

//             document.addEventListener('click', (e) => {
//                 if (!e.target.closest('.menu-button')) {
//                     this.closeAllMenus();
//                 }
//             });
//         }

//         /**
//          * عرض نموذج إنشاء تدفق جديد
//          */
//         showCreateFlowForm() {
//             const flowName = prompt('Enter flow name:');
//             if (!flowName) return;

//             const flowDescription = prompt('Enter flow description (optional):') || '';

//             this.createNewFlow(flowName, flowDescription);
//         }

//         /**
//          * إنشاء تدفق جديد في قاعدة البيانات
//          */
//         async createNewFlow(name, description = '') {
//             try {
//                 const newFlow = {
//                     name: name,
//                     description: description,
//                     config: { nodes: [], connections: [] },
//                     active: false,
//                     count: 0
//                 };

//                 const response = await this.apiPost(`${this.apiBaseUrl}/api/flows/create/`, newFlow);
                
//                 if (response.item) {
//                     this.showSuccess('Automation created successfully');
//                     this.selectedFlowId = response.item.id;
//                     this.showFlowBuilder();
//                 }
//             } catch (error) {
//                 console.error('Error creating flow:', error);
//                 this.showError('Failed to create automation');
//             }
//         }

//         /**
//          * تحميل قائمة التلقائيات من السيرفر
//          */
//         async loadAutomations() {
//             try {
//                 const response = await this.apiGet(`${this.apiBaseUrl}/api/flows/`);
//                 this.flows = response.items || [];
//                 this.renderAutomations(this.flows);
//             } catch (error) {
//                 console.error('Failed to load automations:', error);
//                 this.showError('Failed to load automations list');
//             }
//         }

//         /**
//          * عرض التلقائيات في الواجهة
//          */
//         renderAutomations(flows) {
//             const container = document.getElementById('automations-list');
            
//             if (!flows || flows.length === 0) {
//                 container.innerHTML = `
//                     <div class="empty-state">
//                         <div class="icon">🤖</div>
//                         <h3>No automations yet</h3>
//                         <p>Create your first automation to get started</p>
//                     </div>
//                 `;
//                 return;
//             }

//             container.innerHTML = flows.map(flow => `
//                 <div class="table-row" data-flow-id="${flow.id}">
//                     <div class="flow-name">
//                         <strong>${this.escapeHtml(flow.name)}</strong>
//                         ${flow.description ? `<div class="flow-description">${this.escapeHtml(flow.description)}</div>` : ''}
//                     </div>
//                     <div class="text-center flow-runs">
//                         ${flow.count || 0}
//                     </div>
//                     <div class="text-center flow-status">
//                         <span class="${flow.active ? 'status-active' : 'status-inactive'}">
//                             ${flow.active ? 'Active' : 'Inactive'}
//                         </span>
//                     </div>
//                     <div class="flow-updated">
//                         ${this.formatDate(flow.updated_at || flow.created_at)}
//                     </div>
//                     <div class="text-center actions">
//                         <div class="menu-button">
//                             <button class="btn btn-secondary btn-icon" onclick="automationsList.toggleMenu('${flow.id}')">
//                                 ⋮
//                             </button>
//                             <div class="menu-dropdown" id="menu-${flow.id}">
//                                 <button class="menu-item" onclick="automationsList.toggleFlow('${flow.id}')">
//                                     ${flow.active ? '⏸️ Deactivate' : '▶️ Activate'}
//                                 </button>
//                                 <button class="menu-item" onclick="automationsList.editFlow('${flow.id}')">
//                                     ✏️ Edit
//                                 </button>
//                                 <button class="menu-item" onclick="automationsList.duplicateFlow('${flow.id}')">
//                                     ⎘ Duplicate
//                                 </button>
//                                 <button class="menu-item" style="color: var(--danger);" onclick="automationsList.deleteFlow('${flow.id}')">
//                                     🗑️ Delete
//                                 </button>
//                             </div>
//                         </div>
//                     </div>
//                 </div>
//             `).join('');
//         }

//         /**
//          * تبديل عرض القائمة المنسدلة للعنصر
//          */
//         toggleMenu(flowId) {
//             this.closeAllMenus();
//             const menu = document.getElementById(`menu-${flowId}`);
//             if (menu) {
//                 menu.classList.toggle('show');
//             }
//         }

//         /**
//          * إغلاق جميع القوائم المنسدلة
//          */
//         closeAllMenus() {
//             document.querySelectorAll('.menu-dropdown').forEach(menu => {
//                 menu.classList.remove('show');
//             });
//         }

//         /**
//          * تفعيل/تعطيل التدفق
//          */
//         async toggleFlow(flowId) {
//             try {
//                 const flow = this.flows.find(f => f.id === flowId);
//                 if (!flow) return;

//                 const updatedFlow = {
//                     ...flow,
//                     active: !flow.active
//                 };

//                 const response = await this.apiPost(`${this.apiBaseUrl}/api/flows/${flowId}/update/`, updatedFlow);
                
//                 if (response.item) {
//                     this.showSuccess(`Automation ${updatedFlow.active ? 'activated' : 'deactivated'} successfully`);
//                     this.loadAutomations();
//                 }
//             } catch (error) {
//                 console.error('Error toggling flow:', error);
//                 this.showError('Failed to change automation status');
//             }
//         }

//         /**
//          * تحرير تدفق موجود
//          */
//      /**
//  * تحرير تدفق موجود
//  */
// editFlow(flowId) {
//     this.selectedFlowId = flowId;
//     this.showFlowBuilder();
    
//     // تأكد من تعيين currentFlowId في FlowBuilder
//     if (window.flowBuilder) {
//         setTimeout(() => {
//             window.flowBuilder.currentFlowId = flowId;
//             window.flowBuilder.loadFlow(flowId);
//         }, 100);
//     }
// }/**
//  * تصحيح شامل لبيانات التدفق قبل الإرسال
//  */

//         /**
//          * نسخ تدفق موجود
//          */
//         async duplicateFlow(flowId) {
//             try {
//                 const flow = this.flows.find(f => f.id === flowId);
//                 if (!flow) return;

//                 const newFlow = {
//                     name: `${flow.name} (Copy)`,
//                     description: flow.description ? `${flow.description} (Copy)` : '',
//                     config: flow.config,
//                     active: false,
//                     count: 0
//                 };

//                 const response = await this.apiPost(`${this.apiBaseUrl}/api/flows/create/`, newFlow);
                
//                 if (response.item) {
//                     this.showSuccess('Automation duplicated successfully');
//                     this.loadAutomations();
//                 }
//             } catch (error) {
//                 console.error('Error duplicating flow:', error);
//                 this.showError('Failed to duplicate automation');
//             }
//         }

//         /**
//          * حذف تدفق
//          */
//         async deleteFlow(flowId) {
//             if (confirm('Are you sure you want to delete this automation? This action cannot be undone.')) {
//                 try {
//                     const response = await this.apiPost(`${this.apiBaseUrl}/api/flows/${flowId}/delete/`, {});
                    
//                     if (response.ok) {
//                         this.showSuccess('Automation deleted successfully');
//                         this.loadAutomations();
//                     }
//                 } catch (error) {
//                     console.error('Error deleting flow:', error);
//                     this.showError('Failed to delete automation');
//                 }
//             }
//         }

//         /**
//          * بحث في التلقائيات
//          */
//         searchAutomations(query) {
//             const filteredFlows = this.flows.filter(flow => 
//                 flow.name.toLowerCase().includes(query.toLowerCase()) ||
//                 (flow.description && flow.description.toLowerCase().includes(query.toLowerCase())) ||
//                 (flow.config && JSON.stringify(flow.config).toLowerCase().includes(query.toLowerCase()))
//             );
//             this.renderAutomations(filteredFlows);
//         }

//         /**
//          * عرض واجهة بناء التدفق
//          */
//         showFlowBuilder() {
//             const automationsContainer = document.getElementById('automations-container');
//             const flowBuilderContainer = document.getElementById('flow-builder-container');

//             if (automationsContainer) {
//                 automationsContainer.classList.add('none');
//             }
//             if (flowBuilderContainer) {
//                 flowBuilderContainer.classList.remove('none');
//                 flowBuilderContainer.classList.add('flow-builder-active');
//             }

//             if (typeof flowBuilder !== 'undefined' && flowBuilder) {
//                 if (this.selectedFlowId) {
//                     flowBuilder.loadFlow(this.selectedFlowId);
//                 } else {
//                     flowBuilder.clearCanvas();
//                 }
//             }
//         }

//         /**
//          * العودة إلى قائمة التلقائيات
//          */
//         showAutomationsList() {
//             this.selectedFlowId = null;
            
//             const automationsContainer = document.getElementById('automations-container');
//             const flowBuilderContainer = document.getElementById('flow-builder-container');

//             if (automationsContainer) {
//                 automationsContainer.classList.remove('none');
//             }
//             if (flowBuilderContainer) {
//                 flowBuilderContainer.classList.add('none');
//                 flowBuilderContainer.classList.remove('flow-builder-active');
//             }
//         }

//         /**
//          * طلب GET إلى API
//          */
//         async apiGet(url) {
//             const response = await fetch(url, {
//                 headers: { 'Accept': 'application/json' }
//             });
//             if (!response.ok) throw new Error(`HTTP ${response.status}`);
//             return response.json();
//         }

//         /**
//          * طلب POST إلى API
//          */
//         async apiPost(url, data) {
//             const response = await fetch(url, {
//                 method: 'POST',
//                 headers: {
//                     'Content-Type': 'application/json',
//                     'X-CSRFToken': getCookie('csrftoken')
//                 },
//                 body: JSON.stringify(data)
//             });
            
//             if (!response.ok) {
//                 const error = await response.text();
//                 throw new Error(error || `HTTP ${response.status}`);
//             }
            
//             return response.json();
//         }

//         /**
//          * هروب الأحرار الخاصة في HTML
//          */
//         escapeHtml(text) {
//             const div = document.createElement('div');
//             div.textContent = text;
//             return div.innerHTML;
//         }

//         /**
//          * تنسيق التاريخ
//          */
//         formatDate(dateString) {
//             if (!dateString) return 'Never';
            
//             const date = new Date(dateString);
//             const now = new Date();
//             const diffTime = Math.abs(now - date);
//             const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
            
//             if (diffDays === 1) {
//                 return 'Yesterday';
//             } else if (diffDays < 7) {
//                 return `${diffDays} days ago`;
//             } else {
//                 return date.toLocaleDateString('en-US', {
//                     year: 'numeric',
//                     month: 'short',
//                     day: 'numeric'
//                 });
//             }
//         }

//         /**
//          * عرض رسالة نجاح
//          */
//         showSuccess(message) {
//             this.showNotification(message, 'success');
//         }

//         /**
//          * عرض رسالة خطأ
//          */
//         showError(message) {
//             this.showNotification(message, 'error');
//         }

//         /**
//          * عرض إشعار
//          */
//         showNotification(message, type = 'info') {
//             const notification = document.createElement('div');
//             notification.style.cssText = `
//                 position: fixed;
//                 top: 20px;
//                 right: 20px;
//                 padding: 12px 20px;
//                 border-radius: 8px;
//                 color: white;
//                 font-weight: 500;
//                 z-index: 10000;
//                 transition: all 0.3s ease;
//                 background: ${type === 'success' ? '#10B981' : '#EF4444'};
//                 box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
//             `;
//             notification.textContent = message;
//             document.body.appendChild(notification);

//             setTimeout(() => {
//                 notification.style.opacity = '0';
//                 setTimeout(() => notification.remove(), 300);
//             }, 3000);
//         }
//     }

//     /**
//      * كلاس لبناء التدفقات
//      */
//     class FlowBuilder {
//         constructor() {
//             this.csrfToken = getCookie('csrftoken');
//             this.selectedNode = null;
//             this.nodeCounter = 0;
//             this.currentFlowId = null;
//             this.jsPlumbInstance = null;
//             this.connectionMode = false;
//             this.connectionSource = null;
//             this.zoomLevel = 1.0;
//             this.zoomStep = 0.1;
//             this.minZoom = 0.3;
//             this.maxZoom = 3.0;
            
//             this.initializeElements();
//             this.initializeEventListeners();
//             this.initializeJsPlumb();
//             this.setupDragAndDrop();
//             this.initializeZoom();
//             this.updateStats();
//             // this.createNode(trigger, 8, 21)
//         }

//         /**
//          * تهيئة العناصر الأساسية
//          */
//         initializeElements() {
//             this.flowCanvas = document.getElementById('flow-canvas');
//             this.saveFlowBtn = document.getElementById('save-flow-btn');
//             this.clearBtn = document.getElementById('clear-btn');
//             this.layoutBtn = document.getElementById('layout-btn');
//             this.addVariableBtn = document.getElementById('add-variable-btn');
//             this.sampleFlowBtn = document.getElementById('sample-flow-btn');
            
//             // إخفاء العناصر غير المرغوبة
//             const loadFlowBtn = document.getElementById('load-flow-btn');
//             const flowSelect = document.getElementById('flow-select');
//             const loadExistingBtn = document.getElementById('load-existing-btn');
            
//             if (loadFlowBtn) loadFlowBtn.style.display = 'none';
//             if (flowSelect) flowSelect.style.display = 'none';
//             if (loadExistingBtn) loadExistingBtn.style.display = 'none';
            
//             this.nodeCountEl = document.getElementById('node-count');
//             this.connectionCountEl = document.getElementById('connection-count');
//         }

//         /**
//          * تهيئة مستمعي الأحداث
//          */
//         initializeEventListeners() {
//             this.saveFlowBtn.addEventListener('click', () => this.saveFlow());
//             this.clearBtn.addEventListener('click', () => this.clearCanvas());
//             this.layoutBtn.addEventListener('click', () => this.autoLayout());
//             this.addVariableBtn.addEventListener('click', () => this.addVariable());
//             this.sampleFlowBtn.addEventListener('click', () => this.addSampleFlow());
//         }

//         /**
//          * تهيئة مكتبة jsPlumb
//          */
//         initializeJsPlumb() {
//             if (typeof jsPlumb === 'undefined') {
//                 console.error('jsPlumb not loaded');
//                 return;
//             }

//             this.jsPlumbInstance = jsPlumb.getInstance({
//                 Connector: ["Flowchart", { cornerRadius: 5 }],
//                 PaintStyle: { 
//                     stroke: "#7C3AED", 
//                     strokeWidth: 2,
//                     outlineStroke: "transparent",
//                     outlineWidth: 10
//                 },
//                 EndpointStyle: { 
//                     fill: "#7C3AED",
//                     radius: 5
//                 },
//                 HoverPaintStyle: { 
//                     stroke: "#10B981", 
//                     strokeWidth: 3 
//                 },
//                 ConnectionOverlays: [
//                     ["Arrow", { 
//                         location: 1, 
//                         width: 12, 
//                         length: 12 
//                     }]
//                 ],
//                 Container: "flow-canvas"
//             });

//             this.jsPlumbInstance.bind("connection", (info) => {
//                 this.updateStats();
//             });

//             this.jsPlumbInstance.bind("connectionDetached", (info) => {
//                 this.updateStats();
//             });

//             this.jsPlumbInstance.bind("connection", (conn) => {
//                 conn.bind("click", (connection, originalEvent) => {
//                     if (confirm('Delete this connection?')) {
//                         this.jsPlumbInstance.deleteConnection(connection);
//                         this.showNotification('Connection deleted', 'success');
//                     }
//                 });
//             });
//         }

//         /**
//          * إعداد السحب والإفلات
//          */
//         setupDragAndDrop() {
//             const components = document.querySelectorAll('.component-item');
            
//             components.forEach(component => {
//                 component.addEventListener('dragstart', (e) => {
//                     e.dataTransfer.setData('component-type', component.dataset.type);
//                     e.dataTransfer.effectAllowed = 'copy';
//                 });
//             });

//             this.flowCanvas.addEventListener('dragover', (e) => {
//                 e.preventDefault();
//                 e.dataTransfer.dropEffect = 'copy';
//             });

//             this.flowCanvas.addEventListener('drop', (e) => {
//                 e.preventDefault();
//                 const componentType = e.dataTransfer.getData('component-type');
//                 const rect = this.flowCanvas.getBoundingClientRect();
//                 const x = e.clientX - rect.left - 140;
//                 const y = e.clientY - rect.top - 50;
                
//                 this.createNode(componentType, x, y);
//             });
//         }

//         /**
//          * إنشاء عقدة جديدة
//          */
//         createNode(type, x, y) {
//             this.nodeCounter++;
//             const nodeId = `node-${this.nodeCounter}`;
            
//             const node = document.createElement('div');
//             node.className = 'flow-node';
//             node.id = nodeId;
//             node.dataset.nodeType = type;
//             node.style.left = x + 'px';
//             node.style.top = y + 'px';
            
//             const emptyState = this.flowCanvas.querySelector('.empty-state');
//             if (emptyState) {
//                 emptyState.remove();
//             }
            
//             switch(type) {
//                 case 'text-message':
//                     node.innerHTML = this.createTextMessageNode(nodeId);
//                     break;
//                 case 'media-message':
//                     node.innerHTML = this.createMediaMessageNode(nodeId);
//                     break;
//                 case 'buttons-message':
//                     node.innerHTML = this.createButtonsMessageNode(nodeId);
//                     break;
//                 case 'list-message':
//                     node.innerHTML = this.createListMessageNode(nodeId);
//                     break;
//                 case 'condition':
//                     node.innerHTML = this.createConditionNode(nodeId);
//                     break;
//                 case 'delay':
//                     node.innerHTML = this.createDelayNode(nodeId);
//                     break;
//                 case 'webhook':
//                     node.innerHTML = this.createWebhookNode(nodeId);
//                     break;
//                 case 'add-contact':
//                     node.innerHTML = this.createAddContactNode(nodeId);
//                     break;
//                 case 'update-contact':
//                     node.innerHTML = this.createUpdateContactNode(nodeId);
//                     break;
//                 case 'add-tags':
//                     node.innerHTML = this.createAddTagsNode(nodeId);
//                     break;
//                 case 'remove-tags':
//                     node.innerHTML = this.createRemoveTagsNode(nodeId);
//                     break;
//                 case 'trigger':
//                     node.innerHTML = this.createTriggerNode(nodeId);
//                     break;
//                 default:
//                     node.innerHTML = this.createTextMessageNode(nodeId);
//             }

//             this.flowCanvas.appendChild(node);
//             this.initializeNode(nodeId);
//             this.updateStats();
//             return nodeId;
//         }

//         /**
//          * قوالب العقد المختلفة
//          */
//         createTextMessageNode(nodeId) {
//             return `
//                 <div class="node-header">
//                     <div class="node-icon">📝</div>
//                     <div class="node-title">Text Message</div>
//                     <div class="node-type">text-message</div>
//                 </div>
//                 <div class="node-body">
//                     <div class="node-content">
//                         <textarea class="message-content form-textarea" placeholder="Enter message text..." rows="3">Hello! How can I help you?</textarea>
//                     </div>
//                     <div class="node-properties">
//                         <div class="node-property">
//                             <span>Delay:</span>
//                             <input type="number" value="0" min="0" class="delay-input form-input" style="width: 60px;"> seconds
//                         </div>
//                     </div>
//                 </div>
//                 <div class="node-footer">
//                     <button class="btn btn-secondary btn-sm connect-btn" data-node-id="${nodeId}">Connect</button>
//                     <button class="btn btn-danger btn-sm" onclick="flowBuilder.removeNode('${nodeId}')">Delete</button>
//                 </div>
//             `;
//         }

//         createMediaMessageNode(nodeId) {
//             return `
//                 <div class="node-header">
//                     <div class="node-icon">🖼️</div>
//                     <div class="node-title">Media Message</div>
//                     <div class="node-type">media-message</div>
//                 </div>
//                 <div class="node-body">
//                     <div class="node-content">
//                         <textarea class="caption-content form-textarea" placeholder="Caption (optional)..." rows="2"></textarea>
//                     </div>
//                     <div class="form-group">
//                         <select class="media-type form-select">
//                             <option value="image">Image</option>
//                             <option value="video">Video</option>
//                             <option value="audio">Audio</option>
//                             <option value="file">File</option>
//                         </select>
//                     </div>
//                     <div class="form-group">
//                         <input type="file" class="media-file form-input" accept="image/*,video/*,audio/*,.pdf">
//                     </div>
//                     <div class="node-properties">
//                         <div class="node-property">
//                             <span>Delay:</span>
//                             <input type="number" value="0" min="0" class="delay-input form-input" style="width: 60px;"> seconds
//                         </div>
//                     </div>
//                 </div>
//                 <div class="node-footer">
//                     <button class="btn btn-secondary btn-sm connect-btn" data-node-id="${nodeId}">Connect</button>
//                     <button class="btn btn-danger btn-sm" onclick="flowBuilder.removeNode('${nodeId}')">Delete</button>
//                 </div>
//             `;
//         }

//         createConditionNode(nodeId) {
//             return `
//                 <div class="node-header">
//                     <div class="node-icon">🔀</div>
//                     <div class="node-title">Condition</div>
//                     <div class="node-type">Condition</div>
//                 </div>
//                 <div class="node-body">
//                     <div class="form-group">
//                         <label class="form-label">Variable</label>
//                         <input type="text" class="form-input condition-variable" placeholder="Variable name">
//                     </div>
//                     <div class="form-group">
//                         <label class="form-label">Value</label>
//                         <input type="text" class="form-input condition-value" placeholder="Value to compare">
//                     </div>
//                     <div class="form-group">
//                         <label class="form-label">Comparison Type</label>
//                         <select class="form-select condition-operator">
//                             <option value="equals">Equals</option>
//                             <option value="contains">Contains</option>
//                             <option value="startsWith">Starts With</option>
//                             <option value="endsWith">Ends With</option>
//                             <option value="greaterThan">Greater Than</option>
//                             <option value="lessThan">Less Than</option>
//                         </select>
//                     </div>
//                 </div>
//                 <div class="node-footer">
//                     <button class="btn btn-secondary btn-sm connect-btn" data-node-id="${nodeId}">Connect (True)</button>
//                     <button class="btn btn-secondary btn-sm connect-btn" data-node-id="${nodeId}">Connect (False)</button>
//                     <button class="btn btn-danger btn-sm" onclick="flowBuilder.removeNode('${nodeId}')">Delete</button>
//                 </div>
//             `;
//         }

//         createDelayNode(nodeId) {
//             return `
//                 <div class="node-header">
//                     <div class="node-icon">⏱️</div>
//                     <div class="node-title">Delay</div>
//                     <div class="node-type">Delay</div>
//                 </div>
//                 <div class="node-body">
//                     <div class="form-group">
//                         <label class="form-label">Delay Duration</label>
//                         <input type="number" class="form-input delay-duration" value="5" min="0" max="3600">
//                         <div class="text-muted" style="font-size: 0.75rem; margin-top: 0.25rem;">Seconds</div>
//                     </div>
//                 </div>
//                 <div class="node-footer">
//                     <button class="btn btn-secondary btn-sm connect-btn" data-node-id="${nodeId}">Connect</button>
//                     <button class="btn btn-danger btn-sm" onclick="flowBuilder.removeNode('${nodeId}')">Delete</button>
//                 </div>
//             `;
//         }

//         createTriggerNode(nodeId) {
//             return `
//                 <div class="node-header">
//                     <div class="node-icon">🔔</div>
//                     <div class="node-title">Flow Trigger</div>
//                     <div class="node-type">trigger</div>
//                 </div>
//                 <div class="node-body">
//                     <div class="form-group">
//                         <label class="form-label">Trigger Keywords</label>
//                         <input type="text" class="form-input trigger-keywords" 
//                                placeholder="Enter keywords separated by comma (e.g., hi,hello,help)"
//                                value="hi,hello">
//                         <div class="text-muted" style="font-size: 0.75rem; margin-top: 0.25rem;">
//                             سيبدأ التدفق عندما تحتوي الرسالة على أي من هذه الكلمات
//                         </div>
//                     </div>
//                 </div>
//                 <div class="node-footer">
//                     <button class="btn btn-secondary btn-sm connect-btn" data-node-id="${nodeId}">Connect</button>
//                     <button class="btn btn-danger btn-sm" onclick="flowBuilder.removeNode('${nodeId}')">Delete</button>
//                 </div>
//             `;
//         }

//         // قوالب العقد الأخرى (مختصرة)
//         createButtonsMessageNode(nodeId) { return this.createTextMessageNode(nodeId).replace('Text Message', 'Interactive Buttons'); }
//         createListMessageNode(nodeId) { return this.createTextMessageNode(nodeId).replace('Text Message', 'Interactive List'); }
//         createWebhookNode(nodeId) { return this.createTextMessageNode(nodeId).replace('Text Message', 'Webhook'); }
//         createAddContactNode(nodeId) { return this.createTextMessageNode(nodeId).replace('Text Message', 'Add Contact'); }
//         createUpdateContactNode(nodeId) { return this.createTextMessageNode(nodeId).replace('Text Message', 'Update Contact'); }
//         createAddTagsNode(nodeId) { return this.createTextMessageNode(nodeId).replace('Text Message', 'Add Tags'); }
//         createRemoveTagsNode(nodeId) { return this.createTextMessageNode(nodeId).replace('Text Message', 'Remove Tags'); }


        
//         /**
//          * تهيئة العقدة بعد إنشائها
//          */
//         initializeNode(nodeId) {
//             const node = document.getElementById(nodeId);
//             if (!node || !this.jsPlumbInstance) return;

//             // جعل العقدة قابلة للتحريك
//             this.jsPlumbInstance.draggable(nodeId, {
//                 grid: [10, 10],
//                 stop: () => {
//                     this.saveNodePositions();
//                     setTimeout(() => {
//                         this.jsPlumbInstance.repaintEverything();
//                     }, 10);
//                 }
//             });
            
//             // إضافة نقاط النهاية للاتصالات
//             this.jsPlumbInstance.addEndpoint(nodeId, {
//                 anchor: "Right",
//                 endpoint: "Dot",
//                 paintStyle: { fill: "#7C3AED", radius: 5 },
//                 isSource: true,
//                 maxConnections: 10
//             });
            
//             this.jsPlumbInstance.addEndpoint(nodeId, {
//                 anchor: "Left", 
//                 endpoint: "Dot",
//                 paintStyle: { fill: "#10B981", radius: 5 },
//                 isTarget: true,
//                 maxConnections: 10
//             });
            
//             // إضافة مستمعات الأحداث للأزرار
//             const connectBtns = node.querySelectorAll('.connect-btn');
//             connectBtns.forEach(btn => {
//                 btn.addEventListener('click', (e) => {
//                     e.stopPropagation();
//                     const branch = e.target.dataset.branch;
//                     this.connectNode(nodeId, branch);
//                 });
//             });
            
//             const deleteBtn = node.querySelector('.delete-node-btn');
//             if (deleteBtn) {
//                 deleteBtn.addEventListener('click', (e) => {
//                     e.stopPropagation();
//                     this.removeNode(nodeId);
//                 });
//             }
            
//             node.addEventListener('click', (e) => {
//                 if (!e.target.closest('.connect-btn') && !e.target.closest('.delete-node-btn')) {
//                     this.selectNode(nodeId);
//                 }
//             });

//             // إعادة الرسم الفوري
//             setTimeout(() => {
//                 this.jsPlumbInstance.revalidate(nodeId);
//             }, 50);
//         }

//         /**
//          * تهيئة التحكم في التكبير
//          */
//         // initializeZoom() {
//         //     this.setupZoomEvents();
//         // }

//         /**
//          * إعداد أحداث التكبير
//          */
     
//     initializeZoom() {
//         this.createZoomControls();
//         this.setupZoomEvents();
//     }

//     createZoomControls() {
//         const zoomControls = document.createElement('div');
//         zoomControls.className = 'zoom-controls';
//         zoomControls.innerHTML = `
//             <div class="zoom-buttons">
//                 <button class="btn btn-secondary btn-sm" id="zoom-out" title="Zoom Out (Ctrl + -)">
//                     <span>−</span>
//                 </button>
//                 <span class="zoom-level" id="zoom-level">100%</span>
//                 <button class="btn btn-secondary btn-sm" id="zoom-in" title="Zoom In (Ctrl + +)">
//                     <span>+</span>
//                 </button>
//                 <button class="btn btn-secondary btn-sm" id="zoom-reset" title="Reset Zoom (Ctrl + 0)">
//                     <span>⟳</span>
//                 </button>
//                 <button class="btn btn-secondary btn-sm" id="zoom-fit" title="Fit to Content">
//                     <span>⤢</span>
//                 </button>
//             </div>
//         `;
        
//         const header = document.querySelector('.header-actions');
//         if (header) {
//             header.appendChild(zoomControls);
            
//             document.getElementById('zoom-in').addEventListener('click', () => this.zoomIn());
//             document.getElementById('zoom-out').addEventListener('click', () => this.zoomOut());
//             document.getElementById('zoom-reset').addEventListener('click', () => this.zoomReset());
//             document.getElementById('zoom-fit').addEventListener('click', () => this.zoomToFit());
//         }
//     }

//     setupZoomEvents() {
//         this.flowCanvas.addEventListener('wheel', (e) => {
//             if (e.ctrlKey) {
//                 e.preventDefault();
//                 if (e.deltaY < 0) {
//                     this.zoomIn();
//                 } else {
//                     this.zoomOut();
//                 }
//             }
//         });

//         document.addEventListener('keydown', (e) => {
//             if (e.ctrlKey) {
//                 if (e.key === '=' || e.key === '+') {
//                     e.preventDefault();
//                     this.zoomIn();
//                 } else if (e.key === '-') {
//                     e.preventDefault();
//                     this.zoomOut();
//                 } else if (e.key === '0') {
//                     e.preventDefault();
//                     this.zoomReset();
//                 }
//             }
//         });
//     }

//     zoomIn() {
//         if (this.zoomLevel < this.maxZoom) {
//             this.zoomLevel += this.zoomStep;
//             this.applyZoom();
//         }
//     }

//     zoomOut() {
//         if (this.zoomLevel > this.minZoom) {
//             this.zoomLevel -= this.zoomStep;
//             this.applyZoom();
//         }
//     }

//     zoomReset() {
//         this.zoomLevel = 1.0;
//         this.applyZoom();
//     }

//     applyZoom() {
//         this.flowCanvas.style.transform = `scale(${this.zoomLevel})`;
//         this.flowCanvas.style.transformOrigin = '0 0';
        
//         const zoomLevelEl = document.getElementById('zoom-level');
//         if (zoomLevelEl) {
//             zoomLevelEl.textContent = `${Math.round(this.zoomLevel * 100)}%`;
//         }
        
//         if (this.jsPlumbInstance) {
//             this.jsPlumbInstance.setZoom(this.zoomLevel);
//             setTimeout(() => {
//                 this.jsPlumbInstance.repaintEverything();
//             }, 10);
//         }
//     }

//     zoomToFit() {
//         const nodes = document.querySelectorAll('.flow-node');
//         if (nodes.length === 0) return;
        
//         this.zoomReset();
//         this.autoLayout();
//     }

//     updateStats() {
//         const nodeCount = document.querySelectorAll('.flow-node').length;
//         const connectionCount = this.jsPlumbInstance ? this.jsPlumbInstance.getAllConnections().length : 0;
        
//         if (this.nodeCountEl) this.nodeCountEl.textContent = nodeCount;
//         if (this.connectionCountEl) this.connectionCountEl.textContent = connectionCount;
//     }
//         /**
//          * تكبير
//          */
//         zoomIn() {
//             if (this.zoomLevel < this.maxZoom) {
//                 this.zoomLevel += this.zoomStep;
//                 this.applyZoom();
//             }
//         }

//         /**
//          * تصغير
//          */
//         zoomOut() {
//             if (this.zoomLevel > this.minZoom) {
//                 this.zoomLevel -= this.zoomStep;
//                 this.applyZoom();
//             }
//         }

//         /**
//          * إعادة تعيين التكبير
//          */
//         zoomReset() {
//             this.zoomLevel = 1.0;
//             this.applyZoom();
//         }

//         /**
//          * تطبيق مستوى التكبير
//          */
//         applyZoom() {
//             this.flowCanvas.style.transform = `scale(${this.zoomLevel})`;
//             this.flowCanvas.style.transformOrigin = '0 0';
            
//             const zoomLevelEl = document.getElementById('zoom-level');
//             if (zoomLevelEl) {
//                 zoomLevelEl.textContent = `${Math.round(this.zoomLevel * 100)}%`;
//             }
            
//             if (this.jsPlumbInstance) {
//                 this.jsPlumbInstance.setZoom(this.zoomLevel);
//                 setTimeout(() => {
//                     this.jsPlumbInstance.repaintEverything();
//                 }, 10);
//             }
//         }

//         /**
//          * تكبير ليتناسب مع المحتوى
//          */
//         zoomToFit() {
//             const nodes = document.querySelectorAll('.flow-node');
//             if (nodes.length === 0) return;
            
//             this.zoomReset();
//             this.autoLayout();
//         }





//         /**
//          * تحديث الإحصائيات
//          */
//         updateStats() {
//             const nodeCount = document.querySelectorAll('.flow-node').length;
//             const connectionCount = this.jsPlumbInstance ? this.jsPlumbInstance.getAllConnections().length : 0;
            
//             if (this.nodeCountEl) this.nodeCountEl.textContent = nodeCount;
//             if (this.connectionCountEl) this.connectionCountEl.textContent = connectionCount;
//         }

//         /**
//          * حفظ التدفق
//          */
    
//          /**
//  * حفظ التدفق
//  */
// async saveFlow() {
//     try {
//         let response;
//         const flowData = this.collectFlowData();

//         if (this.currentFlowId) {
//             // ===== تحديث تدفق موجود =====
//             console.log('🔄 تحديث تدفق موجود:', this.currentFlowId);

//             const payload = {
//                 name: this.currentFlowName || '',               // إن كان لديك اسم محفوظ
//                 description: this.currentFlowDescription || '',
//                 config: flowData,
//                 trigger_keywords: this.extractTriggerKeywords(flowData.nodes)
//             };

//             console.log('📦 إرسال بيانات التحديث (PUT):', payload);

//             // استخدام PUT لأن هذا تحديث لمورد موجود
//             response = await fetch(`/discount/whatssapAPI/api/flows/${this.currentFlowId}/update/`, {
//                 method: 'PUT',
//                 headers: {
//                     'Content-Type': 'application/json',
//                     'X-CSRFToken': this.csrfToken
//                 },
//                 body: JSON.stringify(payload)
//             }).then(res => res.json());

//             console.log('🔁 update response raw:', response);

//         } else {
//             // ===== إنشاء تدفق جديد =====
//             console.log('🆕 إنشاء تدفق جديد');
//             const flowName = prompt('Enter flow name:');
//             if (!flowName) return;
//             const flowDescription = prompt('Enter flow description (optional):') || '';

//             const payload = {
//                 name: flowName,
//                 description: flowDescription,
//                 config: flowData,
//                 trigger_keywords: this.extractTriggerKeywords(flowData.nodes)
//             };

//             console.log('📦 إرسال بيانات الإنشاء (POST):', payload);

//             response = await fetch('/discount/whatssapAPI/api/flows/create/', {
//                 method: 'POST',
//                 headers: {
//                     'Content-Type': 'application/json'
//                 },
//                 body: JSON.stringify(payload)
//             }).then(res => res.json());

//             console.log('🔁 create response raw:', response);

//             // قد يختلف اسم المفتاح (item أو flow_id)، لذا افحص الاستجابة بدقة:
//             if (response.success && response.item && response.item.id) {
//                 this.currentFlowId = response.item.id;
//                 this.currentFlowName = flowName;
//                 this.currentFlowDescription = flowDescription;
//             } else if (response.flow_id) {
//                 // بدائل شائعة
//                 this.currentFlowId = response.flow_id;
//                 this.currentFlowName = flowName;
//                 this.currentFlowDescription = flowDescription;
//             } else {
//                 console.warn('Response did not include flow id. Response keys:', Object.keys(response));
//             }
//         }

//         // تحقق من نجاح الاستجابة بحسب هيكل API لديك
//         if (response && (response.success || response.status === 'updated' || response.status === 'ok')) {
//             this.showNotification('Flow saved successfully!', 'success');
//             if (window.automationsList) window.automationsList.loadAutomations();
//         } else {
//             throw new Error(response.error || JSON.stringify(response));
//         }

//     } catch (error) {
//         console.error('❌ Save error:', error);
//         this.showNotification('Failed to save flow: ' + (error.message || error), 'error');
//     }
// }

// /**
//  * استخراج كلمات المحفز من العقد
//  */
// extractTriggerKeywords(nodes) {
//     const triggerNode = nodes.find(node => node.type === 'trigger');
//     if (triggerNode && triggerNode.content && triggerNode.content.keywords) {
//         return triggerNode.content.keywords;
//     }
//     return 'hi,hello'; // قيمة افتراضية
// }

// /**
//  * جمع بيانات التدفق
//  */
//  /**
//  * جمع بيانات التدفق مع تحسينات
//  */
// collectFlowData() {
//     const nodes = Array.from(document.querySelectorAll('.flow-node')).map(node => {
//         const nodeType = node.dataset.nodeType || 'text-message';
//         const nodeData = {
//             id: node.id,
//             type: nodeType,
//             position: {
//                 x: parseInt(node.style.left) || 0,
//                 y: parseInt(node.style.top) || 0
//             },
//             content: this.getNodeContent(node, nodeType)
//         };
        
//         console.log(`📝 Node ${node.id} (${nodeType}):`, nodeData.content);
//         return nodeData;
//     });

//     const connections = this.jsPlumbInstance ? 
//         this.jsPlumbInstance.getAllConnections().map(conn => ({
//             source: conn.sourceId,
//             target: conn.targetId,
//             data: {} // يمكن إضافة بيانات إضافية للاتصال إذا لزم الأمر
//         })) : [];

//     console.log('🔗 Connections:', connections);
    
//     return { 
//         nodes, 
//         connections,
//         metadata: {
//             version: '1.0',
//             created: new Date().toISOString(),
//             nodeCount: nodes.length,
//             connectionCount: connections.length
//         }
//     };
// }
//         /**
//          * استخراج محتوى العقدة حسب نوعها
//          */
//       /**
//  * استخراج محتوى العقدة مع معالجة أفضل للأخطاء
//  */
// getNodeContent(node, nodeType) {
//     const content = {};
    
//     try {
//         switch(nodeType) {
//             case 'trigger':
//                 const keywordsInput = node.querySelector('.trigger-keywords');
//                 content.keywords = keywordsInput ? keywordsInput.value.trim() : 'hi,hello';
//                 break;
                
//             case 'text-message':
//                 const textarea = node.querySelector('textarea');
//                 content.text = textarea ? textarea.value.trim() : '';
                
//                 const delayInput = node.querySelector('.delay-input');
//                 content.delay = delayInput ? parseInt(delayInput.value) || 0 : 0;
//                 break;
                
//             case 'media-message':
//                 content.caption = node.querySelector('textarea')?.value?.trim() || '';
//                 content.mediaType = node.querySelector('.media-type')?.value || 'image';
//                 content.delay = parseInt(node.querySelector('.delay-input')?.value) || 0;
//                 break;
                
//             case 'condition':
//                 content.variable = node.querySelector('.condition-variable')?.value?.trim() || '';
//                 content.value = node.querySelector('.condition-value')?.value?.trim() || '';
//                 content.operator = node.querySelector('.condition-operator')?.value || 'equals';
//                 break;
                
//             case 'delay':
//                 content.duration = parseInt(node.querySelector('.delay-duration')?.value) || 5;
//                 break;
                
//             default:
//                 // للأنواع الأخرى، نجمع كل الحقول النصية
//                 const inputs = node.querySelectorAll('input, textarea, select');
//                 inputs.forEach(input => {
//                     if (input.type !== 'button' && input.type !== 'submit' && !input.classList.contains('connect-btn')) {
//                         const fieldName = this.getFieldName(input);
//                         if (fieldName) {
//                             content[fieldName] = input.value;
//                         }
//                     }
//                 });
//         }
//     } catch (error) {
//         console.error(`❌ Error getting content for node ${node.id}:`, error);
//         content.error = error.message;
//     }
    
//     return content;
// }

// /**
//  * الحصول على اسم الحقل من العنصر
//  */
// getFieldName(element) {
//     const className = element.className;
//     if (className.includes('form-input') || className.includes('form-textarea') || className.includes('form-select')) {
//         // استخراج اسم الحقل من الكلاس
//         const match = className.match(/(?:node-|form-)(\w+)/);
//         return match ? match[1] : element.name || 'unknown';
//     }
//     return null;
// }
//          /**
//          * تحميل تدفق معين
//          */
// async loadFlow(flowId) {
//     try {
//         const response = await this.apiGet(`/discount/whatssapAPI/api/flows/${flowId}/`);
//         console.log('loadFlow response=', response);

//         // عين المعرف قبل render إذا أردت استخدامه أثناء العرض
//         this.currentFlowId = flowId;

//         // احتفظ باسم ووصف إن أرسلت مع الاستجابة
//         if (response.item) {
//             this.currentFlowName = response.item.name || this.currentFlowName;
//             this.currentFlowDescription = response.item.description || this.currentFlowDescription;
//         }

//         this.renderFlow(response.item);
//         this.showNotification('Flow loaded successfully', 'success');
//     } catch (error) {
//         console.error('Load flow error:', error);
//         this.showNotification('Failed to load flow: ' + error.message, 'error');
//     }
// }

// loadConnections(config) {
//     if (!this.jsPlumbInstance || !config.connections) return;

//     config.connections.forEach(c => {
//         const sourceEl = document.getElementById(c.source);
//         const targetEl = document.getElementById(c.target);

//         if (!sourceEl || !targetEl) {
//             console.warn('Skipping connection, element not found:', c.source, c.target);
//             return;
//         }

//         // تحقق من عدم وجود نفس الرابط مسبقًا لتجنب التكرار
//         const existing = this.jsPlumbInstance.getAllConnections().some(conn => 
//             conn.sourceId === c.source && conn.targetId === c.target
//         );
//         if (existing) return;

//         this.jsPlumbInstance.connect({
//             source: sourceEl,
//             target: targetEl,
//             overlays: [["Arrow", { location: 1, width: 12, length: 12 }]],
//             anchors: ["Bottom", "Top"],
//             endpoint: "Dot",
//             paintStyle: { stroke: "#7C3AED", strokeWidth: 2 },
//             hoverPaintStyle: { stroke: "#10B981", strokeWidth: 3 }
//         });
//     });
// }

//         /**
//          * عرض التدفق المحمل
//          */
//         renderFlow(flowData) {
//             this.clearCanvas();
            
//             if (!flowData.config) {
//                 this.showNotification('Invalid flow data', 'error');
//                 return;
//             }
            
//             const nodes = flowData.config.nodes || [];
//             const connections = flowData.config.connections || [];
            
//             console.log('📥 Loading flow with nodes:', nodes);

//             nodes.forEach(nodeData => {
//                 const nodeId = nodeData.id;
//                 if (!nodeId) {
//                     console.error('Node without ID:', nodeData);
//                     return;
//                 }

//                 const node = document.createElement('div');
//                 node.className = 'flow-node';
//                 node.id = nodeId;
//                 node.style.left = (nodeData.position?.x || 100) + 'px';
//                 node.style.top = (nodeData.position?.y || 100) + 'px';
//                 node.dataset.nodeType = nodeData.type;
                
//                 // إنشاء العقدة باستخدام القالب المناسب
//                 const templateFunction = this.getNodeTemplate(nodeData.type);
//                 if (templateFunction) {
//                     node.innerHTML = templateFunction(nodeId);
//                 } else {
//                     node.innerHTML = this.createTextMessageNode(nodeId);
//                 }
                
//                 this.flowCanvas.appendChild(node);
//                 this.initializeNode(nodeId);
                
//                 // تعبئة المحتوى في العقدة
//                 this.fillNodeContent(node, nodeData.content);
//             });
            
//             // إنشاء الاتصالات بعد تأخير بسيط
//             setTimeout(() => {
//                 if (this.jsPlumbInstance) {
//                     connections.forEach(conn => {
//                         this.createConnection(conn.source, conn.target);
//                         console.log('🔗 Created connection from', conn.source, 'to', conn.target);
//                     });
//                     this.jsPlumbInstance.repaintEverything();
//                 }
//                 this.updateStats();
//             }, 700);
//         }

//         /**
//          * الحصول على قالب العقدة حسب النوع
//          */
//         getNodeTemplate(nodeType) {
//             const templates = {
//                 'text-message': this.createTextMessageNode,
//                 'media-message': this.createMediaMessageNode,
//                 'buttons-message': this.createButtonsMessageNode,
//                 'list-message': this.createListMessageNode,
//                 'condition': this.createConditionNode,
//                 'delay': this.createDelayNode,
//                 'webhook': this.createWebhookNode,
//                 'add-contact': this.createAddContactNode,
//                 'update-contact': this.createUpdateContactNode,
//                 'add-tags': this.createAddTagsNode,
//                 'remove-tags': this.createRemoveTagsNode,
//                 'trigger': this.createTriggerNode
//             };
            
//             return templates[nodeType];
//         }

//         /**
//          * تعبئة محتوى العقدة
//          */
//         fillNodeContent(node, content) {
//             if (!content) return;
            
//             const nodeType = node.dataset.nodeType;
//             console.log(`🔄 Filling ${nodeType} node with:`, content);
            
//             switch(nodeType) {
//                 case 'text-message':
//                     const textarea = node.querySelector('textarea');
//                     if (textarea && content.text) textarea.value = content.text;
                    
//                     const delayInput = node.querySelector('.delay-input');
//                     if (delayInput && content.delay !== undefined) delayInput.value = content.delay;
//                     break;
                    
//                 case 'media-message':
//                     const captionTextarea = node.querySelector('textarea');
//                     if (captionTextarea && content.caption) captionTextarea.value = content.caption;
                    
//                     const mediaTypeSelect = node.querySelector('.media-type');
//                     if (mediaTypeSelect && content.mediaType) mediaTypeSelect.value = content.mediaType;
                    
//                     const mediaDelayInput = node.querySelector('.delay-input');
//                     if (mediaDelayInput && content.delay !== undefined) mediaDelayInput.value = content.delay;
//                     break;
                    
//                 case 'condition':
//                     const variableInput = node.querySelector('.condition-variable');
//                     if (variableInput && content.variable) variableInput.value = content.variable;
                    
//                     const valueInput = node.querySelector('.condition-value');
//                     if (valueInput && content.value) valueInput.value = content.value;
                    
//                     const operatorSelect = node.querySelector('.condition-operator');
//                     if (operatorSelect && content.operator) operatorSelect.value = content.operator;
//                     break;
                    
//                 case 'delay':
//                     const durationInput = node.querySelector('.delay-duration');
//                     if (durationInput && content.duration) durationInput.value = content.duration;
//                     break;
                    
//                 case 'trigger':
//                     const keywordsInput = node.querySelector('.trigger-keywords');
//                     if (keywordsInput && content.keywords) keywordsInput.value = content.keywords;
//                     break;
//             }
//         }

//         /**
//          * تصحيح بيانات التدفق
//          */
//   /**
//  * تصحيح شامل لبيانات التدفق قبل الإرسال
//  */
// debugFlowData(flowData) {
//     console.log('🐛 DEBUG Flow Data:');
//     console.log('Total nodes:', flowData.nodes.length);
//     console.log('Total connections:', flowData.connections.length);
    
//     // فحص العقد
//     flowData.nodes.forEach((node, index) => {
//         console.log(`Node ${index + 1}:`, {
//             id: node.id,
//             type: node.type,
//             position: node.position,
//             content: node.content
//         });
        
//         // تحذيرات
//         if (node.type === 'trigger' && (!node.content.keywords || !node.content.keywords.trim())) {
//             console.warn('⚠️ Trigger node has no keywords!');
//         }
//         if (node.type === 'text-message' && (!node.content.text || !node.content.text.trim())) {
//             console.warn('⚠️ Text message node has no text!');
//         }
//     });
    
//     // فحص الاتصالات
//     flowData.connections.forEach((conn, index) => {
//         console.log(`Connection ${index + 1}:`, {
//             source: conn.source,
//             target: conn.target
//         });
//     });
// }

//         /**
//          * حفظ مواقع العقد
//          */
//         saveNodePositions() {
//             // يمكن حفظ مواقع العقد إذا لزم الأمر
//         }

//         /**
//          * إضافة متغير
//          */
//         addVariable() {
//             const variableName = prompt('Enter variable name:');
//             if (!variableName) return;
//             const variableValue = prompt('Enter variable value:');
//             this.showNotification(`Variable added: ${variableName}`, 'success');
//         }

//         /**
//          * مسح اللوحة
//          */
//         clearCanvas() {
//             if (confirm('Are you sure you want to clear the canvas? All nodes and connections will be lost.')) {
//                 document.querySelectorAll('.flow-node').forEach(node => {
//                     if (this.jsPlumbInstance) {
//                         this.jsPlumbInstance.removeAllEndpoints(node.id);
//                     }
//                     node.remove();
//                 });
                
//                 this.nodeCounter = 0;
//                 this.updateStats();
//                 this.showNotification('Canvas cleared successfully', 'success');
//             }
//         }

//         /**
//          * الترتيب التلقائي للعقد
//          */
//         autoLayout() {
//             const nodes = document.querySelectorAll('.flow-node');
//             if (nodes.length === 0) {
//                 this.showNotification('No nodes to arrange', 'warning');
//                 return;
//             }
            
//             const canvasWidth = this.flowCanvas.clientWidth;
//             const nodeWidth = 280;
//             const horizontalSpacing = 100;
//             const verticalSpacing = 120;
            
//             let x = 100;
//             let y = 100;
//             let rowHeight = 0;
            
//             nodes.forEach((node, index) => {
//                 node.style.left = x + 'px';
//                 node.style.top = y + 'px';
                
//                 const nodeHeight = node.offsetHeight;
//                 rowHeight = Math.max(rowHeight, nodeHeight);
                
//                 x += nodeWidth + horizontalSpacing;
                
//                 if (x + nodeWidth > canvasWidth - 100) {
//                     x = 100;
//                     y += rowHeight + verticalSpacing;
//                     rowHeight = 0;
//                 }
                
//                 if (this.jsPlumbInstance) {
//                     this.jsPlumbInstance.revalidate(node.id);
//                 }
//             });
            
//             if (this.jsPlumbInstance) {
//                 this.jsPlumbInstance.repaintEverything();
//             }
//             this.showNotification('Nodes auto-arranged successfully', 'success');
//         }

//         /**
//          * إزالة عقدة
//          */
//         removeNode(nodeId) {
//             if (confirm('Are you sure you want to delete this node?')) {
//                 if (this.jsPlumbInstance) {
//                     this.jsPlumbInstance.removeAllEndpoints(nodeId);
//                     this.jsPlumbInstance.deleteConnectionsForElement(nodeId);
//                 }
                
//                 document.getElementById(nodeId)?.remove();
                
//                 if (this.selectedNode && this.selectedNode.id === nodeId) {
//                     this.selectedNode = null;
//                 }
                
//                 this.updateStats();
//                 this.showNotification('Node deleted', 'success');
//             }
//         }

//         /**
//          * توصيل عقدة
//          */
//         connectNode(nodeId) {
//             if (this.connectionMode && this.connectionSource === nodeId) {
//                 this.cancelConnectionMode();
//             } else {
//                 this.enableConnectionMode(nodeId);
//             }
//         }

//         /**
//          * تفعيل وضع التوصيل
//          */
//         enableConnectionMode(sourceNodeId) {
//             this.connectionMode = true;
//             this.connectionSource = sourceNodeId;
            
//             const sourceNode = document.getElementById(sourceNodeId);
//             if (sourceNode) {
//                 sourceNode.style.boxShadow = '0 0 0 3px #10b981';
//                 sourceNode.classList.add('connection-source');
//             }
            
//             document.body.style.cursor = 'crosshair';
//             this.showNotification('Click on target node to connect. Press ESC to cancel.', 'info');
            
//             this.escapeHandler = (e) => {
//                 if (e.key === 'Escape') {
//                     this.cancelConnectionMode();
//                 }
//             };
//             document.addEventListener('keydown', this.escapeHandler);
            
//             this.connectionClickHandler = (e) => this.handleConnectionTarget(e);
//             this.flowCanvas.addEventListener('click', this.connectionClickHandler);
//         }

//         /**
//          * إلغاء وضع التوصيل
//          */
//         cancelConnectionMode() {
//             this.connectionMode = false;
//             if (this.connectionSource) {
//                 const sourceNode = document.getElementById(this.connectionSource);
//                 if (sourceNode) {
//                     sourceNode.style.boxShadow = '';
//                     sourceNode.classList.remove('connection-source');
//                 }
//             }
//             this.connectionSource = null;
//             document.body.style.cursor = '';
            
//             if (this.escapeHandler) {
//                 document.removeEventListener('keydown', this.escapeHandler);
//             }
//             if (this.connectionClickHandler) {
//                 this.flowCanvas.removeEventListener('click', this.connectionClickHandler);
//             }
            
//             this.showNotification('Connection mode cancelled', 'info');
//         }

//         /**
//          * معالجة الهدف في وضع التوصيل
//          */
//         handleConnectionTarget(e) {
//             if (!this.connectionMode) return;
            
//             const targetNode = e.target.closest('.flow-node');
//             if (!targetNode) return;
            
//             const targetNodeId = targetNode.id;
            
//             if (targetNodeId === this.connectionSource) {
//                 this.showNotification('Cannot connect to the same node', 'error');
//                 return;
//             }
            
//             this.createConnection(this.connectionSource, targetNodeId);
//             this.cancelConnectionMode();
//         }

//         /**
//          * إنشاء اتصال بين عقدتين
//          */
//         createConnection(sourceId, targetId) {
//             if (!this.jsPlumbInstance) return;
            
//             try {
//                 const existingConnections = this.jsPlumbInstance.getConnections({
//                     source: sourceId,
//                     target: targetId
//                 });
                
//                 existingConnections.forEach(conn => {
//                     this.jsPlumbInstance.deleteConnection(conn);
//                 });
                
//                 const connection = this.jsPlumbInstance.connect({
//                     source: sourceId,
//                     target: targetId,
//                     anchors: ["Right", "Left"],
//                     connector: ["Flowchart", { cornerRadius: 5 }],
//                     paintStyle: { 
//                         stroke: "#7C3AED", 
//                         strokeWidth: 2
//                     },
//                     hoverPaintStyle: { stroke: "#10B981", strokeWidth: 3 },
//                     overlays: [
//                         ["Arrow", { 
//                             location: 1, 
//                             width: 12, 
//                             height: 12,
//                             foldback: 0.8 
//                         }]
//                     ]
//                 });
                
//                 this.showNotification(`Connected ${sourceId} to ${targetId}`, 'success');
                
//             } catch (error) {
//                 console.error('Failed to create connection:', error);
//                 this.showNotification('Failed to create connection', 'error');
//             }
//         }

//         /**
//          * تحديد عقدة
//          */
//         selectNode(nodeId) {
//             if (this.selectedNode) {
//                 this.selectedNode.classList.remove('selected');
//             }
            
//             this.selectedNode = document.getElementById(nodeId);
//             if (this.selectedNode) {
//                 this.selectedNode.classList.add('selected');
//             }
//         }

//         /**
//          * إضافة تدفق نموذجي
//          */
//         addSampleFlow() {
//             this.createNode('text-message', 100, 100);
//             this.createNode('condition', 450, 100);
//             this.createNode('text-message', 300, 250);
//             this.createNode('media-message', 600, 250);
//         }

//         /**
//          * طلب GET إلى API
//          */
//         async apiGet(url) {
//             const response = await fetch(url, {
//                 headers: { 'Accept': 'application/json' }
//             });
//             if (!response.ok) throw new Error(`HTTP ${response.status}`);
//             return response.json();
//         }

//         /**
//          * طلب POST إلى API
//          */
//      /**
//  * طلب POST إلى API مع معالجة محسنة للأخطاء
//  */
// async apiPost(url, data) {
//     try {
//         const response = await fetch(url, {
//             method: 'POST',
//             headers: {
//                 'Content-Type': 'application/json',
//                 'X-CSRFToken': this.csrfToken
//             },
//             body: JSON.stringify(data)
//         });

//         if (!response.ok) {
//             let errorMessage = `HTTP ${response.status}`;
//             try {
//                 const errorData = await response.json();
//                 errorMessage = errorData.error || errorData.details || errorMessage;
//             } catch (e) {
//                 const text = await response.text();
//                 errorMessage = text || errorMessage;
//             }
//             throw new Error(errorMessage);
//         }
        
//         return await response.json();
//     } catch (error) {
//         console.error('❌ API POST Error:', error);
//         throw error;
//     }
// }
//         /**
//          * عرض إشعار
//          */
//         showNotification(message, type = 'info') {
//             const notification = document.createElement('div');
//             notification.style.cssText = `
//                 position: fixed;
//                 top: 20px;
//                 right: 20px;
//                 padding: 12px 20px;
//                 border-radius: 8px;
//                 color: white;
//                 font-weight: 500;
//                 z-index: 10000;
//                 transition: all 0.3s ease;
//                 background: ${type === 'success' ? '#10B981' : type === 'error' ? '#EF4444' : '#3B82F6'};
//                 box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
//             `;
//             notification.textContent = message;
//             document.body.appendChild(notification);

//             setTimeout(() => {
//                 notification.style.opacity = '0';
//                 setTimeout(() => notification.remove(), 300);
//             }, 3000);
//         }
//     }

//     // تهيئة التطبيق
//     let automationsList;
//     let flowBuilder;

//     document.addEventListener('DOMContentLoaded', () => {
//         automationsList = new AutomationsList();
        
//         // تهيئة FlowBuilder بعد التأكد من تحميل jsPlumb
//         function initializeFlowBuilder() {
//             if (typeof jsPlumb !== 'undefined') {
//                 flowBuilder = new FlowBuilder();
//                 window.flowBuilder = flowBuilder;
//             } else {
//                 setTimeout(initializeFlowBuilder, 100);
//             }
//         }
        
//         initializeFlowBuilder();
//     });

//     /**
//      * دالة للعودة إلى قائمة التلقائيات
//      */
//     function showAutomationsList() {
//         if (automationsList) {
//             automationsList.showAutomationsList();
//         }
//     }
// </script>