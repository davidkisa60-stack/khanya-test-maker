// ============================================
// Khanya Test Maker - Split Deployment Version
// Frontend: Netlify (static)
// Backend: Render (full Flask)
// ============================================

// === IMPORTANT: Set your Render backend URL here ===
// After deploying the backend to Render, replace this with your live URL (no trailing slash).
// Example: "https://khanya-test-maker.onrender.com"
const BACKEND_URL = "";   // ←←← PUT YOUR RENDER URL HERE (leave empty for local testing / Netlify-only mode)

function getApiUrl(endpoint) {
    if (BACKEND_URL) {
        const base = BACKEND_URL.replace(/\/$/, '');
        return base + endpoint;
    }
    return endpoint;   // relative → works when running local Flask on same origin
}

let allQuestions = [];
let currentSubject = null;
let selectedQuestions = []; // array of question objects
let currentPreview = null;
let currentFilteredQuestions = []; // for filters

const SUBJECTS = ["Mathematics", "Biology", "Physical Science", "English", "Economics", "Development Studies", "Accounting"];

function getSubjectDataPath(subject) {
    const map = {
        "Mathematics": "subjects/mathematics/data/questions.json",
        "Biology": "subjects/biology/data/questions.json",
        "Physical Science": "subjects/physical_science/data/questions.json",
        "English": "subjects/english/data/questions.json",
        "Economics": "subjects/economics/data/questions.json",
        "Development Studies": "subjects/development_studies/data/questions.json",
        "Accounting": "subjects/accounting/data/questions.json"
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

// === CRITICAL: Expose immediately to window after definition ===
window.hideAll = hideAll;
window.showHome = showHome;

function showSubjects() {
    console.log('%c[Khanya] showSubjects() called', 'color:#0ea5e9');
    try {
        hideAll();
        const page = document.getElementById('subjects-page');
        if (!page) {
            console.error('[Khanya] subjects-page not found');
            return;
        }
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

// === CRITICAL: Expose immediately to window after definition ===
window.showSubjects = showSubjects;

async function showSubject(subject) {
    currentSubject = subject;
    selectedQuestions = [];
    currentPreview = null;

    hideAll();
    const page = document.getElementById('subject-page');
    page.classList.remove('hidden');
    page.style.display = 'block';

    document.getElementById('subject-title').textContent = subject;

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
}

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
    renderSelectedList();
    updateSelectedCount();
    const addBtn = document.getElementById('add-btn');
    if (addBtn && currentPreview) {
        addBtn.innerHTML = `<i class="fa-solid fa-plus"></i> <span>Add to Test</span>`;
        addBtn.disabled = false;
    }
}

function previewFullPaper() {
    if (selectedQuestions.length === 0) {
        alert("Please add at least one question.");
        return;
    }

    const modal = document.getElementById('paper-preview-modal');
    const body = document.getElementById('paper-preview-body');
    body.innerHTML = '';

    const title = document.getElementById('paper-title').value.trim() || "Test Paper";
    document.getElementById('modal-paper-title').textContent = title;

    let total = 0;

    selectedQuestions.forEach((q, idx) => {
        total += q.total_marks;
        const section = document.createElement('div');
        section.className = 'mb-8 pb-6 border-b last:border-b-0';

        let bodyText = cleanQuestionBody(q.body_markdown || q.latex || '');
        let html = `
            <div class="flex justify-between mb-2 items-baseline">
                <div class="font-semibold text-base">${idx + 1}. ${q.title}</div>
                <div class="text-sm text-emerald-700 font-medium whitespace-nowrap">${q.total_marks} marks</div>
            </div>
            <div class="math-container text-sm" style="white-space: pre-wrap; line-height: 1.55;">${bodyText.replace(/\n/g, '<br>')}</div>
        `;
        if (q.images && q.images.length) {
            html += `<div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">`;
            q.images.forEach(img => {
                html += `<img src="assets/images/${img}" class="border border-zinc-200 rounded-xl max-h-56 object-contain bg-white" alt="Diagram" style="max-width:100%; height:auto;">`;
            });
            html += `</div>`;
        }
        html += `<div class="text-[10px] text-zinc-400 mt-1 italic">— space for workings —</div>`;

        section.innerHTML = html;
        body.appendChild(section);
    });

    document.getElementById('modal-total-marks').textContent = total;
    modal.classList.remove('hidden');
    modal.classList.add('flex');
}

function closePaperPreview() {
    const modal = document.getElementById('paper-preview-modal');
    modal.classList.remove('flex');
    modal.classList.add('hidden');
}

async function downloadFullPaperPDF() {
    if (selectedQuestions.length === 0) return;

    const ids = selectedQuestions.map(q => q.id);
    const title = document.getElementById('paper-title').value.trim() || `${currentSubject || 'Test'} Paper`;

    const apiUrl = getApiUrl('/api/generate-pdf');

    try {
        const res = await fetch(apiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ids: ids,
                title: title,
                subject: currentSubject || 'Mathematics'
            })
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
            return;
        } else {
            const err = await res.json().catch(() => ({}));
            console.warn('PDF API error:', err);
            alert('PDF generation failed: ' + (err.error || res.statusText));
        }
    } catch (e) {
        console.warn('PDF download error:', e);
    }

    const idsStr = ids.join(',');
    alert(
        `PDF download failed.\n\n` +
        `This usually means the backend is not connected.\n\n` +
        `Options:\n` +
        `1. Set BACKEND_URL in js/app.js to your Render URL and redeploy frontend.\n` +
        `2. Use CLI: python generate_paper.py --subject "${currentSubject || 'Mathematics'}" --ids ${idsStr} --title "${title}"\n` +
        `3. Run locally: python flask_app.py (then use http://127.0.0.1:5001)`
    );
}

async function downloadFullPaperDocx() {
    if (selectedQuestions.length === 0) return;

    const ids = selectedQuestions.map(q => q.id);
    const title = document.getElementById('paper-title').value.trim() || `${currentSubject || 'Test'} Paper`;

    const apiUrl = getApiUrl('/api/generate-docx');

    try {
        const res = await fetch(apiUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ids: ids,
                title: title,
                subject: currentSubject || 'Mathematics'
            })
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
            return;
        } else {
            const err = await res.json().catch(() => ({}));
            console.warn('DOCX API error:', err);
            alert('Word generation failed: ' + (err.error || res.statusText));
        }
    } catch (e) {
        console.warn('DOCX download error:', e);
    }

    const idsStr = ids.join(',');
    alert(
        `Word download failed.\n\n` +
        `This usually means the backend is not connected.\n\n` +
        `Options:\n` +
        `1. Set BACKEND_URL in js/app.js to your Render URL and redeploy frontend.\n` +
        `2. Use CLI: python generate_paper.py --subject "${currentSubject || 'Mathematics'}" --ids ${idsStr} --title "${title}" --format docx\n` +
        `3. Run locally: python flask_app.py (then use http://127.0.0.1:5001)`
    );
}

// === Attach listeners from JS (most reliable) + text fallback ===
function attachNewTestButtons() {
    let nav = document.getElementById('btn-new-test-nav');
    if (!nav) {
        nav = Array.from(document.querySelectorAll('button, a')).find(el => 
            el.textContent && el.textContent.trim().toLowerCase().includes('new test') && 
            !el.id.includes('big')
        );
    }
    if (nav) {
        nav.onclick = null;
        const handler = (e) => {
            e.preventDefault();
            console.log('%c[Khanya] New Test nav clicked', 'color:#0ea5e9');
            (window.showSubjects || showSubjects)();
        };
        nav.addEventListener('click', handler);
    }

    let big = document.getElementById('btn-new-test-big');
    if (big) {
        big.onclick = null;
        big.addEventListener('click', (e) => {
            e.preventDefault();
            console.log('%c[Khanya] New Test big clicked', 'color:#0ea5e9');
            (window.showSubjects || showSubjects)();
        });
    }
}

// === Boot with aggressive retries ===
function boot() {
    console.log('%c[Khanya] Booted (Split deployment ready)', 'color:#16a34a');
    
    if (window.showHome) {
        window.showHome();
    } else {
        showHome();
    }
    
    attachNewTestButtons();
    setTimeout(attachNewTestButtons, 200);
    setTimeout(attachNewTestButtons, 600);
    setTimeout(attachNewTestButtons, 1200);
    setTimeout(attachNewTestButtons, 2500);

    document.addEventListener('click', function(e) {
        const target = e.target;
        const isNewTestBtn = target && (
            target.id === 'btn-new-test-nav' || 
            target.id === 'btn-new-test-big' ||
            (target.closest && (target.closest('#btn-new-test-nav') || target.closest('#btn-new-test-big'))) ||
            (target.textContent && target.textContent.trim().toLowerCase() === 'new test' && (target.tagName === 'BUTTON' || target.closest('button')))
        );
        if (isNewTestBtn) {
            e.preventDefault();
            console.log('%c[Khanya] Document fallback: New Test clicked', 'color:#0ea5e9');
            (window.showSubjects || showSubjects)();
        }
    }, true);
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
} else {
    boot();
}