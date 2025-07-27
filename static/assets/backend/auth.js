// Зберігає токен у cookie
function saveToken(token, maxAge = 3600) { // maxAge is in seconds (default: 1 hour)
    document.cookie = `access_token=${token}; Path=/; Max-Age=${maxAge}; HttpOnly; Secure`;
}

// Отримує токен із cookie
function getToken() {
    const cookies = document.cookie.split('; ');
    for (let cookie of cookies) {
        const [name, value] = cookie.split('=');
        if (name === 'access_token') {
            return value;
        }
    }
    return null; // Повертає null, якщо токен відсутній
}

// Видаляє токен із cookie
function removeToken() {
    document.cookie = `access_token=; Path=/; Max-Age=0; HttpOnly; Secure`;
}

// Виконує запит із токеном
function authorizedFetch(url, options = {}) {
    const token = getToken(); // Отримати токен із cookie
    const headers = options.headers || {};

    if (token) {
        headers['Authorization'] = `Bearer ${token}`; // Додаємо токен до заголовків
        console.log(`Authorized fetch token: ${headers['Authorization']}`); // Debug: Log the token
    }

    options.headers = headers;

    return fetch(url, options);
}

// Функція для перевірки авторизації на сторінках
function checkAuthorization() {
    const token = getToken();
    if (!token) {
        // Якщо токен відсутній, перенаправляємо на сторінку логіну
        window.location.href = '/';
    }
}

// Експортуємо функції для використання в інших скриптах
export { saveToken, getToken, removeToken, authorizedFetch, checkAuthorization };