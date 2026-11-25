// ===== Состояние приложения =====
const state = {
    user: null,
    tests: [],
    current: null,   // { id, title }
    questions: [],
    answers: {},     // { question_id: индекс_варианта }
    index: 0,
    quizTimer: null,
    quizDeadline: null,
    isSubmitting: false,
};

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str ?? '';
    return div.innerHTML;
}

// Обёртка над fetch: при 401 возвращает пользователя на экран входа
async function api(url, options = {}) {
    const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    if (res.status === 401 && !url.startsWith('/api/login')) {
        setUser(null);
    }
    return res;
}

// ===== Навигация между экранами =====
function showView(name) {
    $$('.view').forEach((v) => (v.hidden = true));
    $(`#view-${name}`).hidden = false;

    const navName = name === 'editor' ? 'admin' : name;  // в редакторе подсвечиваем пункт «Панель»
    $$('.nav__link').forEach((l) =>
        l.classList.toggle('is-active', l.dataset.nav === navName)
    );
    window.scrollTo({ top: 0, behavior: 'smooth' });

    if (name === 'home' && state.user) loadTests();  // список всегда свежий (преподаватель мог добавить тест)
    if (name === 'history') loadHistory();
    if (name === 'admin' && window.Admin) Admin.open();
}

document.addEventListener('click', (e) => {
    const nav = e.target.closest('[data-nav]');
    if (nav) {
        e.preventDefault();
        if (state.user) showView(nav.dataset.nav);
    }
});

// ===== Авторизация =====
function setUser(user) {
    state.user = user;
    const header = $('#app-header');
    if (user) {
        header.hidden = false;
        $('#user-name').textContent = user.username;
        $('#user-avatar').textContent = user.username.charAt(0);
        // Пункт «Панель» виден только преподавателям и администраторам (права всё равно проверяет сервер)
        $('#nav-admin').hidden = !['teacher', 'admin'].includes(user.role);
        $('#tab-users').hidden = user.role !== 'admin';
        showView('home');
    } else {
        header.hidden = true;
        state.tests = [];
        showAuthTab('login');
        showView('auth');
    }
}

function showAuthTab(tab) {
    $$('.tabs__btn').forEach((b) => b.classList.toggle('is-active', b.dataset.tab === tab));
    $('#form-login').hidden = tab !== 'login';
    $('#form-register').hidden = tab !== 'register';
    hideAuthError();
}

function showAuthError(msg) {
    const box = $('#auth-error');
    box.textContent = msg;
    box.hidden = false;
}

function hideAuthError() {
    $('#auth-error').hidden = true;
}

$$('.tabs__btn').forEach((b) => (b.onclick = () => showAuthTab(b.dataset.tab)));
$$('[data-tab-link]').forEach((a) =>
    a.addEventListener('click', (e) => {
        e.preventDefault();
        showAuthTab(a.dataset.tabLink);
    })
);

$('#form-login').onsubmit = async (e) => {
    e.preventDefault();
    hideAuthError();
    const form = e.target;
    try {
        const res = await api('/api/login', {
            method: 'POST',
            body: JSON.stringify({
                username: form.username.value,
                password: form.password.value,
            }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) return showAuthError(data.error || 'Ошибка сервера. Смотрите консоль, где запущен app.py');
        form.reset();
        setUser(data);
    } catch {
        showAuthError('Нет связи с сервером');
    }
};

$('#form-register').onsubmit = async (e) => {
    e.preventDefault();
    hideAuthError();
    const form = e.target;
    if (form.password.value !== form.password2.value) {
        return showAuthError('Пароли не совпадают');
    }
    try {
        const res = await api('/api/register', {
            method: 'POST',
            body: JSON.stringify({
                username: form.username.value,
                email: form.email.value,
                password: form.password.value,
            }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) return showAuthError(data.error || 'Ошибка сервера. Смотрите консоль, где запущен app.py');
        form.reset();
        setUser(data);
    } catch {
        showAuthError('Нет связи с сервером');
    }
};

$('#btn-logout').onclick = async () => {
    await api('/api/logout', { method: 'POST' });
    setUser(null);
};

// ===== Список тестов =====
async function loadTests() {
    const grid = $('#tests-grid');
    grid.innerHTML = '<div class="state-msg">Загрузка тестов...</div>';
    $('#search').value = '';
    try {
        const res = await api('/api/tests');
        if (!res.ok) throw new Error();
        state.tests = await res.json();
        renderTests(state.tests);
    } catch {
        grid.innerHTML = '<div class="state-msg">Не удалось загрузить тесты. Проверьте сервер и базу данных.</div>';
    }
}

function renderTests(list) {
    const grid = $('#tests-grid');
    const query = $('#search').value.trim().toLowerCase();
    const filtered = list.filter((t) => t.title.toLowerCase().includes(query));
    if (!filtered.length) {
        grid.innerHTML = '<div class="state-msg">Тесты не найдены.</div>';
        return;
    }
    grid.innerHTML = '';
    filtered.forEach((t) => {
        const card = document.createElement('div');
        card.className = 'card test-card';
        card.innerHTML = `
            <div class="test-card__top">
                <div class="test-card__badge" aria-hidden="true">📝</div>
                <span class="test-card__type">${(t.test_type || 'choice') === 'matching' ? 'На соответствие' : 'С выбором ответа'}</span>
            </div>
            <h3>${escapeHtml(t.title)}</h3>
            <div class="test-card__details">
                <span class="test-card__duration">${t.duration_minutes ? `⏱ ${t.duration_minutes} мин` : 'Без ограничения времени'}</span>
                <span class="test-card__author">Автор: ${escapeHtml(t.author || 'Не указан')}</span>
            </div>
            <p class="test-card__description">${escapeHtml(t.description || 'Описание отсутствует')}</p>
            <button class="btn btn--primary test-card__action"><span>Пройти тест</span><span aria-hidden="true">→</span></button>`;
        card.querySelector('button').onclick = () => startTest(t);
        grid.appendChild(card);
    });
}

$('#search').addEventListener('input', (e) => {
    renderTests(state.tests);
});

// ===== Прохождение теста =====
async function startTest(test) {
    try {
        const res = await api(`/api/tests/${test.id}/questions`);
        if (!res.ok) throw new Error();
        const questions = await res.json();
        if (!questions.length) {
            alert('В этом тесте пока нет вопросов.');
            return;
        }
        state.current = test;
        state.questions = questions;
        state.answers = {};
        state.index = 0;
        state.isSubmitting = false;
        $('#quiz-title').textContent = test.title;
        showView('quiz');
        startQuizTimer(test.duration_minutes);
        renderQuestion();
    } catch {
        alert('Не удалось загрузить вопросы.');
    }
}

function stopQuizTimer() {
    if (state.quizTimer) clearInterval(state.quizTimer);
    state.quizTimer = null;
    state.quizDeadline = null;
    $('#quiz-timer').hidden = true;
}

function startQuizTimer(durationMinutes) {
    stopQuizTimer();
    if (!Number.isInteger(durationMinutes) || durationMinutes < 1) return;
    const timer = $('#quiz-timer');
    timer.innerHTML = `
        <span class="quiz__timer-icon" aria-hidden="true">⏱</span>
        <span>Осталось</span>
        <span class="quiz__timer-value"></span>`;
    const timerValue = timer.querySelector('.quiz__timer-value');
    timer.hidden = false;
    timer.classList.remove('is-urgent');
    state.quizDeadline = Date.now() + durationMinutes * 60 * 1000;
    const update = () => {
        const remaining = Math.max(0, Math.ceil((state.quizDeadline - Date.now()) / 1000));
        const minutes = Math.floor(remaining / 60);
        const seconds = remaining % 60;
        timerValue.textContent = `${minutes}:${String(seconds).padStart(2, '0')}`;
        timerValue.classList.remove('is-ticking');
        void timerValue.offsetWidth;
        timerValue.classList.add('is-ticking');
        timer.classList.toggle('is-urgent', remaining <= 60);
        if (remaining === 0) {
            clearInterval(state.quizTimer);
            state.quizTimer = null;
            finishTest();
        }
    };
    update();
    state.quizTimer = setInterval(update, 1000);
}

function renderQuestion() {
    const q = state.questions[state.index];
    const total = state.questions.length;

    $('#quiz-counter').textContent = `Вопрос ${state.index + 1} из ${total}`;
    $('#progress-bar').style.width = `${((state.index + 1) / total) * 100}%`;
    $('#question-text').textContent = q.question_text;

    const box = $('#options');
    box.innerHTML = '';
    if (q.question_type === 'matching') {
        box.className = 'matching-answer';
        if (!state.answers[q.id]) state.answers[q.id] = {};
        q.left_items.forEach((left, leftIndex) => {
            const row = document.createElement('div');
            row.className = 'matching-answer__row';
            row.innerHTML = `
                <span class="matching-answer__left">${escapeHtml(left)}</span>
                <span class="matching-answer__arrow">→</span>
                <select class="matching-answer__select">
                    <option value="">Выберите соответствие</option>
                    ${q.right_items.map((right, rightIndex) =>
                        `<option value="${rightIndex}" ${state.answers[q.id][leftIndex] === rightIndex ? 'selected' : ''}>${escapeHtml(right)}</option>`
                    ).join('')}
                </select>`;
            row.querySelector('select').onchange = (e) => {
                state.answers[q.id][leftIndex] = e.target.value === '' ? undefined : Number(e.target.value);
                renderQuestion();
            };
            box.appendChild(row);
        });
    } else {
        box.className = 'options';
        q.options.forEach((opt, i) => {
            const label = document.createElement('label');
            label.className = 'option' + (state.answers[q.id] === i ? ' is-selected' : '');
            label.innerHTML = `<input type="radio" name="opt"><span class="option__dot"></span><span>${escapeHtml(opt)}</span>`;
            label.onclick = (e) => {
                e.preventDefault();
                state.answers[q.id] = i;
                renderQuestion();
            };
            box.appendChild(label);
        });
    }

    $('#btn-prev').disabled = state.index === 0;
    const isLast = state.index === total - 1;
    const btnNext = $('#btn-next');
    btnNext.textContent = isLast ? 'Завершить' : 'Далее';
    if (q.question_type === 'matching') {
        const mapping = state.answers[q.id] || {};
        btnNext.disabled = q.left_items.some((_, i) => mapping[i] === undefined);
    } else {
        btnNext.disabled = state.answers[q.id] === undefined;
    }
}

$('#btn-prev').onclick = () => {
    if (state.index > 0) {
        state.index--;
        renderQuestion();
    }
};

$('#btn-next').onclick = () => {
    if (state.index < state.questions.length - 1) {
        state.index++;
        renderQuestion();
    } else {
        finishTest();
    }
};

$('#btn-exit').onclick = () => {
    if (confirm('Выйти из теста? Ответы не сохранятся.')) {
        stopQuizTimer();
        showView('home');
    }
};

async function finishTest() {
    if (state.isSubmitting) return;
    state.isSubmitting = true;
    stopQuizTimer();
    const btn = $('#btn-next');
    btn.disabled = true;
    try {
        const res = await api('/api/submit', {
            method: 'POST',
            body: JSON.stringify({
                test_id: state.current.id,
                answers: state.answers,
            }),
        });
        if (!res.ok) throw new Error();
        const result = await res.json();
        $('#result-title').textContent = state.current.title;
        $('#result-score').textContent = result.score;
        showView('result');
    } catch {
        alert('Не удалось сохранить результат. Попробуйте ещё раз.');
        state.isSubmitting = false;
        btn.disabled = false;
    }
}

// ===== История результатов =====
async function loadHistory() {
    const box = $('#history-list');
    box.innerHTML = '<div class="state-msg">Загрузка...</div>';
    try {
        const res = await api('/api/results');
        if (!res.ok) throw new Error();
        const rows = await res.json();
        if (!rows.length) {
            box.innerHTML = '<div class="state-msg">Вы ещё не проходили тесты.</div>';
            return;
        }
        box.innerHTML = rows
            .map(
                (r) => `
            <div class="history__row">
                <div>
                    <div class="history__title">${escapeHtml(r.title)}</div>
                    <div class="history__date">${r.created_at ? new Date(r.created_at).toLocaleString('ru-RU') : ''}</div>
                </div>
                <div class="history__score">${r.score}</div>
            </div>`
            )
            .join('');
    } catch {
        box.innerHTML = '<div class="state-msg">Не удалось загрузить результаты.</div>';
    }
}

// ===== Старт: проверяем, вошёл ли пользователь =====
(async function init() {
    try {
        const res = await fetch('/api/me');
        const data = await res.json();
        setUser(data.authenticated ? { id: data.id, username: data.username, role: data.role } : null);
    } catch {
        setUser(null);
    }
})();
