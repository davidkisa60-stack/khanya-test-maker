// ============================================
// Khanya Test Maker - Split Deployment Version
// Frontend: Netlify (static) + Login Protection
// Backend: Render (full Flask)
// ============================================

// ===== ULTRA-AGGRESSIVE IMMEDIATE LOGIN PROTECTION (exact match to admin.html) =====
// This MUST be the VERY FIRST executable code (before any const/let/function).
// Synchronous check at parse time. If no valid khanya_user.email → instant replace + stop.
// Authenticated → reveal the page immediately (exact same as admin.html + index.html head script).
(function() {
    var user = null;
    try {
        var raw = localStorage.getItem('khanya_user');
        if (raw) user = JSON.parse(raw);
    } catch (e) {}

    if (!user || !user.email) {
        // Redirect instantly. Nothing will render.
        window.location.replace('/login');
        return;
    }

    // Authenticated user - reveal the page immediately
    document.documentElement.style.cssText = 'display:block !important; visibility:visible !important; opacity:1 !important;';
    document.body.style.cssText = 'display:block !important; visibility:visible !important; opacity:1 !important;';
})();

const BACKEND_URL = "";   // ←←← PUT YOUR RENDER URL HERE

function getApiUrl(endpoint) {
    if (BACKEND_URL) {
        const base = BACKEND_URL.replace(/\//$, '');
        return base + endpoint;
    }
    return endpoint;
}

let allQuestions = [];
let currentSubject = null;
let selectedQuestions = [];

window.selectedQuestions = selectedQuestions;
window.currentSubject = currentSubject;

let currentPreview = null;
let currentFilteredQuestions = [];

function _exposeSelected() {
    window.selectedQuestions = selectedQuestions;
}
window._exposeSelected = _exposeSelected;

function syncSelectedToWindow() {
    window.selectedQuestions = selectedQuestions;
    try {
        Object.defineProperty(window, 'selectedQuestions', {
            get: () => selectedQuestions,
            set: (v) => { selectedQuestions = v; },
            configurable: true
        });
    } catch(e) {}
}
window.syncSelectedToWindow = syncSelectedToWindow;

function syncCurrentSubjectToWindow() {
    window.currentSubject = currentSubject;
}
window.syncCurrentSubjectToWindow = syncCurrentSubjectToWindow;

const SUBJECTS = ["Mathematics", "Biology", "Physical Science", "Economics", "Development Studies", "Accounting", "English"];

function getSubjectDataPath(subject) {
    const map = {
        "Mathematics": "subjects/mathematics/data/questions.json",
        "Biology": "subjects/biology/data/questions.json",
        "Physical Science": "subjects/physical_science/data/questions.json",
        "Economics": "subjects/economics/data/questions.json",
        "Development Studies": "subjects/development_studies/data/questions.json",
        "Accounting": "subjects/accounting/data/questions.json",
        "English": "subjects/english/data/questions.json"
    };
    return map[subject] || "data/questions.json";
}

async function loadQuestions(subject = "Mathematics") {
    const path = getSubjectDataPath(subject);
    try {
        const res = await fetch(path);
        allQuestions = await res.json();
        console.log(`Loaded ${allQuestions.length} questions for ${subject} from ${path}`);
    } catch (e) {
        console.error(`Failed to load questions for ${subject} from ${path}`);
        allQuestions = [];
    }
}

function hideAll() {
    ['home-page', 'subjects-page', 'subject-page', 'paper-preview-modal'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.classList.add('hidden');
            el.style.display = 'none';
        }
    });
}

function showHome() {
    hideAll();
    const home = document.getElementById('home-page');
    if (home) {
        home.classList.remove('hidden');
        home.style.display = 'block';
    }
}

window.hideAll = hideAll;
window.showHome = showHome;

function showSubjects() {
    console.log('%c[Khanya] showSubjects() called', 'color:#0ea5e9');
    try {
        hideAll();
        const page = document.getElementById('subjects-page');
        if (!page) return;
        page.classList.remove('hidden');
        page.style.display = 'block';

        const grid = document.getElementById('subjects-grid');
        if (!grid) return;
        grid.innerHTML = '';

        SUBJECTS.forEach(subject => {
            const isMath = subject === 'Mathematics';
            const card = document.createElement('div');
            card.className = `bg-white border border-zinc-200 rounded-3xl p-5 cursor-pointer hover:shadow-md transition ${isMath ? 'ring-2 ring-emerald-500' : 'opacity-80'}`;
            card.innerHTML = `
                <div class="flex items-center gap-x-3">
                    <i class="fa-solid fa-book text-2xl ${isMath ? 'text-emerald-600' : 'text-zinc-400'}"></i>
                    <div class="font-semibold text-lg">${subject}</div>
                </div>
            `;
            card.onclick = () => showSubject(subject);
            grid.appendChild(card);
        });
    } catch (e) {
        console.error('[Khanya] showSubjects error', e);
    }
}

window.showSubjects = showSubjects;

async function showSubject(subject) {
    currentSubject = subject;
    window.currentSubject = subject;
    syncCurrentSubjectToWindow();
    selectedQuestions = [];
    syncSelectedToWindow();
    currentPreview = null;

    hideAll();
    const page = document.getElementById('subject-page');
    page.classList.remove('hidden');
    page.style.display = 'block';

    document.getElementById('subject-title').textContent = subject;

    const paperTitleInput = document.getElementById('paper-title');
    if (paperTitleInput) {
        paperTitleInput.value = `${subject} Test`;
    }

    const topicsEl = document.getElementById('topics-list');
    topicsEl.innerHTML = '';

    await loadQuestions(subject);

    if (allQuestions.length === 0) {
        topicsEl.innerHTML = `<div class="p-6 text-center text-zinc-400">
            <i class="fa-solid fa-info-circle text-3xl mb-3"></i><br>
            No questions extracted for ${subject} yet.
        </div>`;
        document.getElementById('selected-list').innerHTML = '<div class="text-xs text-zinc-400 p-3 text-center">No questions selected.</div>';
        updateSelectedCount();
        return;
    }

    populateFilterDropdowns();
    renderFilteredTopics();
    renderSelectedList();
    showPreviewPlaceholder();
    updateSelectedCount();

    setTimeout(attachPreviewButton, 50);
    setTimeout(attachPreviewButton, 300);
}

// ... (rest of the original app.js functions remain unchanged from here down)
// The rest of the file is kept identical to preserve all existing functionality.

function populateFilterDropdowns() {
    const years = [...new Set(allQuestions.map(q => q.year))].sort((a,b)=>b-a);
    const papers = [...new Set(allQuestions.map(q => q.paper))].sort();
    const topics = [...new Set(allQuestions.map(q => q.topic))].sort();

    const ysel = document.getElementById('filter-year');
    if (ysel) {
        ysel.innerHTML = '<option value="">All years</option>';
        years.forEach(y => ysel.append(new Option(y, y)));
    }
    const psel = document.getElementById('filter-paper');
    if (psel) {
        psel.innerHTML = '<option value="">All papers</option>';
        papers.forEach(p => psel.append(new Option(p, p)));
    }
    const tsel = document.getElementById('filter-topic');
    if (tsel) {
        tsel.innerHTML = '<option value="">All topics</option>';
        topics.forEach(t => tsel.append(new Option(t, t)));
    }
}

function getFilteredQuestions() {
    const search = (document.getElementById('filter-search')?.value || '').toLowerCase().trim();
    const year = document.getElementById('filter-year')?.value || '';
    const paper = document.getElementById('filter-paper')?.value || '';
    const topic = document.getElementById('filter-topic')?.value || '';

    return allQuestions.filter(q => {
        const okS = !search || q.title.toLowerCase().includes(search) || (q.body_markdown||'').toLowerCase().includes(search) || q.id.toLowerCase().includes(search);
        return okS && (!year || String(q.year) === year) && (!paper || q.paper === paper) && (!topic || q.topic === topic);
    });
}

function applyFilters() { renderFilteredTopics(); }

function clearFilters() {
    ['filter-search','filter-year','filter-paper','filter-topic'].forEach(id => {
        const el = document.getElementById(id); if(el) el.value='';
    });
    renderFilteredTopics();
}

function renderFilteredTopics() {
    const topicsEl = document.getElementById('topics-list');
    if (!topicsEl) return;
    topicsEl.innerHTML = '';

    const filtered = getFilteredQuestions();
    currentFilteredQuestions = filtered;

    const byTopic = {};
    filtered.forEach(q => { (byTopic[q.topic] ||= []).push(q); });

    const order = ["Number","Algebra","Geometry","Sets","Probability","Statistics","Surds","Bearings"];
    Object.keys(byTopic).sort((a,b) => (order.indexOf(a)+999) - (order.indexOf(b)+999)).forEach(topic => {
        let qs = byTopic[topic].sort((a,b) => (b.year||0)-(a.year||0) || (a.original_num||0)-(b.original_num||0));

        const wrapper = document.createElement('div');
        wrapper.className = 'border border-zinc-200 rounded-2xl mb-2 bg-white overflow-hidden';

        const header = document.createElement('div');
        header.className = 'topic-header flex items-center justify-between px-4 py-2.5 bg-zinc-50 cursor-pointer hover:bg-zinc-100';
        header.innerHTML = `
            <div class="font-medium flex items-center gap-x-2 text-sm">
                <i class="fa-solid fa-folder text-emerald-600"></i>
                <span>${topic}</span>
                <span class="text-xs text-zinc-500">(${qs.length})</span>
            </div>
            <i class="fa-solid fa-chevron-down text-zinc-400"></i>
        `;

        const content = document.createElement('div');
        content.className = 'hidden border-t p-1';

        qs.forEach(q => {
            const item = document.createElement('div');
            item.className = 'question-item flex items-center justify-between px-3 py-2 hover:bg-zinc-50 rounded-xl cursor-pointer text-sm';
            const pl = q.paper ? ` <span class="ml-1.5 px-1.5 py-0.5 text-[9px] bg-zinc-100 text-zinc-500 rounded">${q.paper}</span>` : '';
            item.innerHTML = `
                <div class="flex-1 truncate pr-2"><span class="font-mono text-xs text-blue-700">${q.id}</span> ${q.title}${pl}</div>
                <div class="flex items-center gap-x-1 ml-2">
                    <button class="text-xs px-2.5 py-1 border border-zinc-200 hover:bg-white rounded-lg" onclick="event.stopImmediatePropagation(); previewQuestion('${q.id}')">Preview</button>
                    <button class="text-xs px-2.5 py-1 bg-emerald-600 text-white hover:bg-emerald-700 rounded-lg" onclick="event.stopImmediatePropagation(); addToSelection('${q.id}')">Add</button>
                </div>
            `;
            content.appendChild(item);
        });

        header.onclick = () => {
            content.classList.toggle('hidden');
            const ch = header.querySelector('.fa-chevron-down');
            if (ch) ch.classList.toggle('fa-chevron-up');
        };

        wrapper.appendChild(header);
        wrapper.appendChild(content);
        topicsEl.appendChild(wrapper);
    });

    const cnt = document.getElementById('filter-count');
    if (cnt) cnt.textContent = '';
}

function showPreviewPlaceholder() {
    const ph = document.getElementById('preview-placeholder');
    const c = document.getElementById('preview-content');
    if (ph) ph.classList.remove('hidden');
    if (c) c.classList.add('hidden');
}

function cleanQuestionBody(body) {
    if (!body) return '';
    let cleaned = body;
    cleaned = cleaned.replace(/\.{3,}\s*\[\d+\]/g, '');
    cleaned = cleaned.replace(/\s*\[\d+\]/g, '');
    cleaned = cleaned.replace(/\$/g, '').replace(/\\times/g, '×').replace(/\\pi/g, 'π').replace(/\\/g, '');
    cleaned = cleaned.replace(/\n{3,}/g, '\n\n').trim();
    return cleaned;
}

function previewQuestion(qid) {
    const q = allQuestions.find(x => x.id === qid);
    if (!q) return;
    currentPreview = q;

    const ph = document.getElementById('preview-placeholder');
    const content = document.getElementById('preview-content');
    if (ph) ph.classList.add('hidden');
    if (content) content.classList.remove('hidden');

    document.getElementById('preview-title').textContent = q.title;
    const paperInfo = q.paper ? ` · ${q.paper}` : '';
    document.getElementById('preview-marks').textContent = `${q.total_marks} marks${paperInfo}`;

    const bodyEl = document.getElementById('preview-body');
    let bodyText = cleanQuestionBody(q.body_markdown || q.latex || '');
    bodyEl.innerHTML = `<div class="math-container" style="white-space: pre-wrap; line-height: 1.55; font-size: 0.93rem;">${bodyText.replace(/\n/g, '<br>')}</div>`;

    const imgContainer = document.getElementById('preview-images');
    imgContainer.innerHTML = '';
    if (q.images && q.images.length) {
        q.images.forEach(img => {
            const d = document.createElement('div');
            d.innerHTML = `<img src="assets/images/${img}" class="w-full border border-zinc-200 rounded-xl max-h-56 object-contain bg-white" alt="Diagram for ${q.title}">`;
            imgContainer.appendChild(d);
        });
    } else {
        imgContainer.innerHTML = '<div class="text-xs text-zinc-400">No diagram attached to this question.</div>';
    }

    const addBtn = document.getElementById('add-btn');
    const already = selectedQuestions.some(s => s.id === q.id);
    addBtn.innerHTML = already 
        ? `<i class="fa-solid fa-check"></i> <span>Added</span>` 
        : `<i class="fa-solid fa-plus"></i> <span>Add to Test</span>`;
    addBtn.disabled = already;
}

function addToSelection(qid) {
    const q = allQuestions.find(x => x.id === qid);
    if (!q || selectedQuestions.some(s => s.id === q.id)) return;

    selectedQuestions.push(q);
    syncSelectedToWindow();
    renderSelectedList();
    updateSelectedCount();

    const addBtn = document.getElementById('add-btn');
    if (addBtn && currentPreview && currentPreview.id === qid) {
        addBtn.innerHTML = `<i class="fa-solid fa-check"></i> <span>Added</span>`;
        addBtn.disabled = true;
    }
}

function addCurrentToSelection() {
    if (currentPreview) addToSelection(currentPreview.id);
}

function renderSelectedList() {
    const container = document.getElementById('selected-list');
    container.innerHTML = '';

    if (selectedQuestions.length === 0) {
        container.innerHTML = `<div class="text-xs text-zinc-400 p-3 text-center">No questions added yet.</div>`;
        return;
    }

    selectedQuestions.forEach((q, i) => {
        const div = document.createElement('div');
        div.className = 'flex items-center justify-between bg-zinc-50 border border-zinc-200 rounded-2xl px-3 py-1.5 mb-1 text-sm';
        const paperTag = q.paper ? `<span class="text-[9px] px-1 py-px bg-white border text-zinc-400 rounded ml-1.5">${q.paper}</span>` : '';
        div.innerHTML = `
            <div class="flex items-center gap-x-2 min-w-0">
                <span class="font-mono text-xs bg-white px-1.5 rounded border">${q.id}</span>
                <span class="truncate">${q.title}</span>${paperTag}
            </div>
            <div class="flex items-center gap-x-2">
                <span class="text-emerald-700 text-xs font-medium">${q.total_marks}m</span>
                <button onclick="removeFromSelection(${i})" class="text-red-500 hover:text-red-700 px-1">×</button>
            </div>
        `;
        container.appendChild(div);
    });
}

function removeFromSelection(index) {
    selectedQuestions.splice(index, 1);
    syncSelectedToWindow();
    renderSelectedList();
    updateSelectedCount();

    const addBtn = document.getElementById('add-btn');
    if (addBtn && currentPreview) {
        const already = selectedQuestions.some(s => s.id === currentPreview.id);
        addBtn.innerHTML = already 
            ? `<i class="fa-solid fa-check"></i> <span>Added</span>` 
            : `<i class="fa-solid fa-plus"></i> <span>Add to Test</span>`;
        addBtn.disabled = already;
    }
}

function updateSelectedCount() {
    const el = document.getElementById('selected-count');
    if (el) el.textContent = selectedQuestions.length;
}

function clearSelection() {
    selectedQuestions = [];
    syncSelectedToWindow();
    renderSelectedList();
    updateSelectedCount();
    const addBtn = document.getElementById('add-btn');
    if (addBtn && currentPreview) {
        addBtn.innerHTML = `<i class="fa-solid fa-plus"></i> <span>Add to Test</span>`;
        addBtn.disabled = false;
    }
}

function previewFullPaper() {
    console.log('%c[Khanya] === previewFullPaper() ENTERED ===', 'color:#eab308; font-weight:bold');
    let questions = selectedQuestions;
    if ((!questions || questions.length === 0) && window.selectedQuestions && window.selectedQuestions.length > 0) {
        questions = window.selectedQuestions;
    }

    if (!questions || questions.length === 0) {
        alert("Please add questions first using the green 'Add' buttons.");
        return;
    }

    const modal = document.getElementById('paper-preview-modal');
    const body = document.getElementById('paper-preview-body');
    const titleEl = document.getElementById('modal-paper-title');
    const totalEl = document.getElementById('modal-total-marks');

    if (!modal || !body) return;

    body.innerHTML = '';

    const paperTitle = document.getElementById('paper-title')?.value.trim() || "Test Paper";
    if (titleEl) titleEl.textContent = paperTitle;

    let total = 0;

    questions.forEach((q, idx) => {
        const marks = Number(q.total_marks) || 0;
        total += marks;

        const section = document.createElement('div');
        section.className = 'mb-8 pb-6 border-b last:border-b-0';

        const bodyText = cleanQuestionBody(q.body_markdown || q.latex || '');

        let html = `
            <div class="flex justify-between mb-2 items-baseline">
                <div class="font-semibold text-base">${idx + 1}. ${q.title || 'Untitled'}</div>
                <div class="text-sm text-emerald-700 font-medium">${marks} marks</div>
            </div>
            <div class="math-container text-sm" style="white-space: pre-wrap; line-height: 1.55;">${bodyText.replace(/\n/g, '<br>')}</div>
        `;

        if (q.images && q.images.length > 0) {
            html += `<div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">`;
            q.images.forEach(img => {
                html += `<img src="assets/images/${img}" class="border border-zinc-200 rounded-xl max-h-56 object-contain bg-white" style="max-width:100%; height:auto;" onerror="this.style.display='none'">`;
            });
            html += `</div>`;
        }

        html += `<div class="text-[10px] text-zinc-400 mt-1 italic">— space for workings —</div>`;

        section.innerHTML = html;
        body.appendChild(section);
    });

    if (totalEl) totalEl.textContent = total;

    modal.classList.remove('hidden');
    modal.classList.add('flex');
    modal.style.display = 'flex';
    modal.style.visibility = 'visible';
    modal.style.opacity = '1';
    modal.style.pointerEvents = 'auto';
}

window.previewFullPaper = previewFullPaper;

function closePaperPreview() {
    const modal = document.getElementById('paper-preview-modal');
    if (!modal) return;

    modal.classList.remove('flex');
    modal.classList.add('hidden');
    modal.removeAttribute('style');
    modal.style.cssText = '';
    modal.style.setProperty('display', 'none', 'important');
}

window.closePaperPreview = closePaperPreview;

// Download functions (keep your existing ones)
async function downloadFullPaperPDF() {
    if (selectedQuestions.length === 0) return;

    let subj = currentSubject || window.currentSubject || 'Mathematics';
    const ids = selectedQuestions.map(q => q.id);
    const title = document.getElementById('paper-title').value.trim() || `${subj} Paper`;
    const apiUrl = getApiUrl('/api/generate-pdf');

    try {
        const res = await fetch(apiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids, title, subject: subj })
        });

        if (res.ok) {
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${title.replace(/\s+/g, '_')}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            setTimeout(() => (window.closePaperPreview || closePaperPreview)(), 30);
            return;
        }
    } catch (e) {}

    alert("PDF download failed. Make sure the backend is running.");
}

async function downloadFullPaperDocx() {
    if (selectedQuestions.length === 0) return;

    let subj = currentSubject || window.currentSubject || 'Mathematics';
    const ids = selectedQuestions.map(q => q.id);
    const title = document.getElementById('paper-title').value.trim() || `${subj} Paper`;
    const apiUrl = getApiUrl('/api/generate-docx');

    try {
        const res = await fetch(apiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ids, title, subject: subj })
        });

        if (res.ok) {
            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${title.replace(/\s+/g, '_')}.docx`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            setTimeout(() => (window.closePaperPreview || closePaperPreview)(), 30);
            return;
        }
    } catch (e) {}

    alert("Word download failed.");
}

window.downloadFullPaperPDF = downloadFullPaperPDF;
window.downloadFullPaperDocx = downloadFullPaperDocx;

// Keep all your other functions (attachPreviewButton, boot, etc.) exactly as they were.
// For brevity they are omitted here but must remain unchanged in your actual file.

function attachPreviewButton() { /* keep your original */ }
function boot() { /* keep your original */ }

// Start
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
} else {
    boot();
}