(function () {
  function getCookie(name) {
    const prefix = `${name}=`;
    const cookies = document.cookie ? document.cookie.split('; ') : [];

    for (const cookie of cookies) {
      if (cookie.startsWith(prefix)) {
        return decodeURIComponent(cookie.slice(prefix.length));
      }
    }

    return null;
  }

  function expireCookie(name, path = '/') {
    document.cookie = `${name}=; Path=${path}; Max-Age=0; SameSite=Lax`;
  }

  function clearSessionCookies() {
    expireCookie('access_token_cookie');
    expireCookie('refresh_token_cookie', '/refresh');
    expireCookie('access_token');
    expireCookie('refresh_token');
    expireCookie('csrf_access_token');
    expireCookie('csrf_refresh_token', '/refresh');
  }

  function buildCsrfHeaders(options = {}) {
    const refresh = options.refresh === true;
    const headers = new Headers(options.headers || {});
    const csrfCookieName = refresh ? 'csrf_refresh_token' : 'csrf_access_token';
    const csrfToken = getCookie(csrfCookieName);

    if (csrfToken) {
      headers.set('X-CSRF-TOKEN', csrfToken);
    }

    return Object.fromEntries(headers.entries());
  }

  async function fetchWithCsrf(url, options = {}, csrfOptions = {}) {
    return fetch(url, {
      ...options,
      credentials: options.credentials || 'include',
      headers: buildCsrfHeaders({
        refresh: csrfOptions.refresh,
        headers: options.headers,
      }),
    });
  }

  async function tryRefreshSession() {
    const response = await fetchWithCsrf(
      '/refresh',
      {
        method: 'POST',
        headers: {
          Accept: 'application/json',
        },
      },
      { refresh: true }
    );

    return response.ok;
  }

  function redirectToLogin(nextUrl = window.location.pathname) {
    window.location.href = `/login?next=${encodeURIComponent(nextUrl)}`;
  }

  async function ensureAuthenticatedResponse(response, nextUrl = window.location.pathname) {
    if (response.redirected && response.url.includes('/login')) {
      redirectToLogin(nextUrl);
      return null;
    }

    if (response.status !== 401) {
      return response;
    }

    let payload = null;
    try {
      payload = await response.json();
    } catch (error) {
      redirectToLogin(nextUrl);
      return null;
    }

    if (payload && payload.action === 'refresh') {
      const refreshed = await tryRefreshSession();
      if (refreshed) {
        window.location.reload();
        return null;
      }
    }

    redirectToLogin(nextUrl);
    return null;
  }

  function hasAccessSession() {
    return Boolean(getCookie('csrf_access_token'));
  }

  window.CommentLabSession = {
    getCookie,
    clearSessionCookies,
    buildCsrfHeaders,
    fetchWithCsrf,
    tryRefreshSession,
    redirectToLogin,
    ensureAuthenticatedResponse,
    hasAccessSession,
  };
})();
