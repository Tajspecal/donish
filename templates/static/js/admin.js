// ===== Панель преподавателя: тесты, редактор, импорт файла, генерация, пользователи =====
// Подключается после app.js и использует его функции: api(), showView(), escapeHtml(), $, $$, state.
window.Admin = (function () {
    const ROLES = { student: 'Студент', teacher: 'Преподаватель', admin: 'Администратор' };
    const SOURCES = { manual: 'Вручную', import: 'Из файла', gemini: 'Gemini' };
    const MIN_OPTIONS = 2;
    const MAX_OPTIONS = 6;

    let tests = [];
    let draft = null; // { id, source, title, description, questions: [{question_text, options, correct_answer}] }

    // ---------- Вспомогательные ----------
    function notice(msg, isError = true) {
        const box = $('#admin-notice');
        box.textContent = msg || '';
        box.hidden = !msg;
        box.classList.toggle('alert--info', !isError);
    }

    async function call(url, options) {
        const res = await api(url, options);
        const data = await res.json().catch(() => ({}));
        return { ok: res.ok, status: res.status, data };
    }

    function formatDate(s) {
        if (!s) return '—';
        const d = new Date(s.replace(' ', 'T') + 'Z');
        return isNaN(d) ? '—' : d.toLocaleDateString('ru-RU');
    }

    const emptyQuestion = () => ({ question_text: '', options: ['', ''], correct_answer: 0 });

    // ---------- Вкладки ----------
    function openTab(name) {
        $$('#admin-tabs .tabs__btn').forEach((b) => b.classList.toggle('is-active', b.dataset.adminTab === name));
        $('#admin-tests').hidden = name !== 'tests';
        $('#admin-users').hidden = name !== 'users';
        notice('');
        if (name === 'users') loadUsers();
        else loadTests();
    }

    $$('#admin-tabs .tabs__btn').forEach((b) => (b.onclick = () => openTab(b.dataset.adminTab)));

    function open() {
        openTab('tests');
    }

    // ---------- Список тестов ----------
    async function loadTests() {
        const box = $('#admin-tests-list');
        box.innerHTML = '<div class="state-msg">Загрузка...</div>';
        const r = await call('/api/admin/tests');
        if (!r.ok) {
            box.innerHTML = `<div class="state-msg">${escapeHtml(r.data.error || 'Не удалось загрузить тесты')}</div>`;
            return;
        }
        tests = r.data;
        renderTests();
    }

    function renderTests() {
        const q = $('#admin-search').value.trim().toLowerCase();
        const list = tests.filter((t) => t.title.toLowerCase().includes(q));
        const box = $('#admin-tests-list');
        if (!list.length) {
            box.innerHTML = '<div class="state-msg">Тесты не найдены.</div>';
            return;
        }
        box.innerHTML = `
            <table class="table">
                <thead><tr><th>Название</th><th>Вопросов</th><th>Источник</th><th>Автор</th><th>Создан</th><th></th></tr></thead>
                <tbody>${list.map((t) => `
                    <tr>
                        <td data-label="Название"><strong>${escapeHtml(t.title)}</strong>
                            <div class="muted small">${escapeHtml(t.description || '')}</div></td>
                        <td data-label="Вопросов">${t.questions}</td>
                        <td data-label="Источник"><span class="badge badge--${t.source}">${SOURCES[t.source] || t.source}</span></td>
                        <td data-label="Автор">${escapeHtml(t.author || '—')}</td>
                        <td data-label="Создан">${formatDate(t.created_at)}</td>
                        <td class="table__actions">
                            <button class="btn btn--secondary btn--small" data-results="${t.id}">Результаты</button>
                            <button class="btn btn--secondary btn--small" data-edit="${t.id}">Изменить</button>
                            <button class="btn btn--danger btn--small" data-del="${t.id}">Удалить</button>
                        </td>
                    </tr>`).join('')}
                </tbody>
            </table>`;
        box.querySelectorAll('[data-results]').forEach((b) => (b.onclick = () => showResults(+b.dataset.results)));
        box.querySelectorAll('[data-edit]').forEach((b) => (b.onclick = () => editTest(+b.dataset.edit)));
        box.querySelectorAll('[data-del]').forEach((b) => (b.onclick = () => deleteTest(+b.dataset.del)));
    }

    $('#admin-search').addEventListener('input', renderTests);

    async function showResults(id) {
        const test = tests.find((x) => x.id === id);
        const box = $('#admin-results');
        const list = $('#admin-results-list');
        $('#admin-results-title').textContent = `Результаты: ${test ? test.title : 'тест'}`;
        box.hidden = false;
        list.innerHTML = '<div class="state-msg">Загрузка...</div>';
        box.scrollIntoView({ behavior: 'smooth', block: 'start' });
        const r = await call(`/api/admin/tests/${id}/results`);
        if (!r.ok) {
            list.innerHTML = `<div class="state-msg">${escapeHtml(r.data.error || 'Не удалось загрузить результаты')}</div>`;
            return;
        }
        if (!r.data.length) {
            list.innerHTML = '<div class="state-msg">Студенты этот тест ещё не проходили.</div>';
            return;
        }
        list.innerHTML = `
            <table class="table">
                <thead><tr><th>Студент</th><th>Результат</th><th>Дата</th></tr></thead>
                <tbody>${r.data.map((row) => `
                    <tr>
                        <td data-label="Студент"><strong>${escapeHtml(row.username)}</strong></td>
                        <td data-label="Результат">${row.score}%</td>
                        <td data-label="Дата">${formatDate(row.created_at)}</td>
                    </tr>`).join('')}
                </tbody>
            </table>`;
    }

    $('#btn-close-results').onclick = () => {
        $('#admin-results').hidden = true;
    };

    async function deleteTest(id) {
        const t = tests.find((x) => x.id === id);
        if (!confirm(`Удалить тест «${t.title}»? Вместе с ним удалятся вопросы и результаты студентов.`)) return;
        const r = await call(`/api/admin/tests/${id}`, { method: 'DELETE' });
        if (!r.ok) return notice(r.data.error || 'Не удалось удалить тест');
        notice('Тест удалён.', false);
        loadTests();
    }

    // ---------- Импорт из файла ----------
    $('#btn-import-file').onclick = () => $('#import-file').click();

    $('#import-file').onchange = async (e) => {
        const file = e.target.files[0];
        e.target.value = '';
        if (!file) return;
        try {
            const data = JSON.parse(await file.text());
            openEditor({
                id: null,
                source: 'import',
                title: data.title || '',
                description: data.description || '',
                questions: Array.isArray(data.questions) ? data.questions : [],
            }, 'Файл загружен. Проверьте вопросы и нажмите «Сохранить тест».');
        } catch {
            notice('Не удалось прочитать файл: он должен быть в формате JSON.');
        }
    };

    // ---------- Генерация через Gemini ----------
    const generator = $('#generator');
    $('#btn-open-generator').onclick = () => {
        generator.hidden = !generator.hidden;
        if (!generator.hidden) generator.topic.focus();
    };
    $('#btn-close-generator').onclick = () => (generator.hidden = true);

    generator.onsubmit = async (e) => {
        e.preventDefault();
        notice('');
        const btn = $('#btn-generate');
        const status = $('#generator-status');
        btn.disabled = true;
        status.textContent = 'Gemini готовит вопросы, это может занять до минуты...';
        try {
            const r = await call('/api/admin/generate', {
                method: 'POST',
                body: JSON.stringify({
                    topic: generator.topic.value,
                    count: generator.count.value,
                    options: generator.options.value,
                    difficulty: generator.difficulty.value,
                    language: generator.language.value,
                }),
            });
            if (!r.ok) return notice(r.data.error || 'Не удалось сгенерировать тест. Смотрите консоль сервера.');
            generator.hidden = true;
            const msg = 'Черновик создан Gemini и ещё не сохранён. Модель может ошибаться — проверьте вопросы и правильные ответы.'
                + (r.data.warning ? ' ' + r.data.warning : '');
            openEditor({ id: null, source: 'gemini', title: r.data.title, description: r.data.description,
                         questions: r.data.questions }, msg);
        } catch {
            notice('Нет связи с сервером');
        } finally {
            btn.disabled = false;
            status.textContent = '';
        }
    };

    // ---------- Редактор теста ----------
    function openEditor(d, infoText) {
        draft = {
            id: d.id,
            source: d.source,
            title: d.title,
            description: d.description,
            questions: d.questions.map((q) => ({
                question_text: q.question_text ?? '',
                options: Array.isArray(q.options) ? q.options.map(String) : ['', ''],
                correct_answer: Number.isInteger(q.correct_answer) ? q.correct_answer : 0,
            })),
        };
        if (!draft.questions.length) draft.questions.push(emptyQuestion());
        $('#editor-title').textContent = d.id ? 'Редактирование теста' : d.source === 'manual' ? 'Новый тест' : 'Проверка черновика';
        $('#editor-name').value = draft.title;
        $('#editor-desc').value = draft.description;
        const info = $('#editor-notice');
        info.textContent = infoText || '';
        info.hidden = !infoText;
        setEditorError('');
        renderEditor();
        showView('editor');
    }

    async function editTest(id) {
        const r = await call(`/api/admin/tests/${id}`);
        if (!r.ok) return notice(r.data.error || 'Не удалось загрузить тест');
        openEditor(r.data);
    }

    $('#btn-new-test').onclick = () => openEditor({ id: null, source: 'manual', title: '', description: '', questions: [] });

    function setEditorError(msg) {
        const box = $('#editor-error');
        box.textContent = msg || '';
        box.hidden = !msg;
    }

    function renderEditor() {
        const box = $('#editor-questions');
        box.innerHTML = '';
        draft.questions.forEach((q, qi) => {
            const card = document.createElement('div');
            card.className = 'card qcard';
            card.innerHTML = `
                <div class="qcard__head">
                    <strong>Вопрос ${qi + 1}</strong>
                    <button type="button" class="btn btn--danger btn--small" data-act="del-q">Удалить вопрос</button>
                </div>
                <textarea class="qcard__text" rows="2" placeholder="Текст вопроса"></textarea>
                <div class="qcard__hint muted small">Отметьте кружком правильный вариант ответа</div>
                <div class="qcard__options"></div>
                <button type="button" class="btn btn--secondary btn--small qcard__add" data-act="add-opt">+ Вариант</button>`;
            const text = card.querySelector('textarea');
            text.value = q.question_text;
            text.oninput = () => (q.question_text = text.value);

            const optBox = card.querySelector('.qcard__options');
            q.options.forEach((opt, oi) => {
                const row = document.createElement('div');
                row.className = 'opt';
                row.innerHTML = `
                    <input type="radio" name="correct-${qi}" title="Правильный ответ" ${q.correct_answer === oi ? 'checked' : ''}>
                    <input type="text" class="opt__text" placeholder="Вариант ${oi + 1}">
                    <button type="button" class="btn btn--ghost btn--small opt__del" title="Удалить вариант"
                        ${q.options.length <= MIN_OPTIONS ? 'disabled' : ''}>✕</button>`;
                const input = row.querySelector('.opt__text');
                input.value = opt;
                input.oninput = () => (q.options[oi] = input.value);
                row.querySelector('input[type=radio]').onchange = () => (q.correct_answer = oi);
                row.querySelector('.opt__del').onclick = () => {
                    q.options.splice(oi, 1);
                    if (q.correct_answer === oi) q.correct_answer = 0;
                    else if (q.correct_answer > oi) q.correct_answer--;
                    renderEditor();
                };
                optBox.appendChild(row);
            });

            const addOpt = card.querySelector('[data-act=add-opt]');
            addOpt.disabled = q.options.length >= MAX_OPTIONS;
            addOpt.onclick = () => { q.options.push(''); renderEditor(); };
            card.querySelector('[data-act=del-q]').onclick = () => {
                draft.questions.splice(qi, 1);
                if (!draft.questions.length) draft.questions.push(emptyQuestion());
                renderEditor();
            };
            box.appendChild(card);
        });
    }

    $('#btn-add-question').onclick = () => {
        draft.questions.push(emptyQuestion());
        renderEditor();
        const cards = $$('#editor-questions .qcard');
        cards[cards.length - 1].scrollIntoView({ behavior: 'smooth', block: 'center' });
    };

    function leaveEditor() {
        draft = null;
        showView('admin');
    }
    $('#btn-editor-back').onclick = $('#btn-editor-cancel').onclick = () => {
        if (confirm('Выйти без сохранения? Несохранённые изменения пропадут.')) leaveEditor();
    };

    $('#btn-editor-save').onclick = async () => {
        draft.title = $('#editor-name').value;
        draft.description = $('#editor-desc').value;
        const payload = JSON.stringify({
            title: draft.title,
            description: draft.description,
            questions: draft.questions,
            source: draft.source,
        });
        const btn = $('#btn-editor-save');
        btn.disabled = true;
        try {
            let r;
            if (draft.id) r = await call(`/api/admin/tests/${draft.id}`, { method: 'PUT', body: payload });
            else if (draft.source === 'manual') r = await call('/api/admin/tests', { method: 'POST', body: payload });
            else r = await call('/api/admin/import', { method: 'POST', body: payload });
            if (!r.ok) {
                setEditorError(r.data.error || 'Не удалось сохранить тест');
                window.scrollTo({ top: 0, behavior: 'smooth' });
                return;
            }
            leaveEditor();
            notice('Тест сохранён.', false);
            state.tests = []; // список для студентов обновится при следующем входе на главную
        } catch {
            setEditorError('Нет связи с сервером');
        } finally {
            btn.disabled = false;
        }
    };

    // ---------- Пользователи ----------
    async function loadUsers() {
        const box = $('#admin-users-list');
        box.innerHTML = '<div class="state-msg">Загрузка...</div>';
        const r = await call('/api/admin/users');
        if (!r.ok) {
            box.innerHTML = `<div class="state-msg">${escapeHtml(r.data.error || 'Не удалось загрузить пользователей')}</div>`;
            return;
        }
        box.innerHTML = `
            <table class="table">
                <thead><tr><th>Логин</th><th>Email</th><th>Роль</th><th>Регистрация</th><th></th></tr></thead>
                <tbody>${r.data.map((u) => `
                    <tr>
                        <td data-label="Логин"><strong>${escapeHtml(u.username)}</strong></td>
                        <td data-label="Email">${escapeHtml(u.email)}</td>
                        <td data-label="Роль">
                            <select class="select" data-role="${u.id}" ${u.id === state.user.id ? 'disabled' : ''}>
                                ${Object.entries(ROLES).map(([k, v]) => `<option value="${k}" ${u.role === k ? 'selected' : ''}>${v}</option>`).join('')}
                            </select></td>
                        <td data-label="Регистрация">${formatDate(u.created_at)}</td>
                        <td class="table__actions">
                            ${u.id === state.user.id ? '<span class="muted small">это вы</span>'
                                : `<button class="btn btn--danger btn--small" data-deluser="${u.id}" data-name="${escapeHtml(u.username)}">Удалить</button>`}
                        </td>
                    </tr>`).join('')}
                </tbody>
            </table>`;
        box.querySelectorAll('[data-role]').forEach((sel) => {
            sel.onchange = async () => {
                const res = await call(`/api/admin/users/${sel.dataset.role}/role`, {
                    method: 'PUT',
                    body: JSON.stringify({ role: sel.value }),
                });
                notice(res.ok ? 'Роль изменена.' : res.data.error || 'Не удалось изменить роль', !res.ok);
                if (!res.ok) loadUsers();
            };
        });
        box.querySelectorAll('[data-deluser]').forEach((b) => {
            b.onclick = async () => {
                if (!confirm(`Удалить пользователя «${b.dataset.name}» вместе с его результатами?`)) return;
                const res = await call(`/api/admin/users/${b.dataset.deluser}`, { method: 'DELETE' });
                notice(res.ok ? 'Пользователь удалён.' : res.data.error || 'Не удалось удалить', !res.ok);
                loadUsers();
            };
        });
    }

    return { open };
})();
