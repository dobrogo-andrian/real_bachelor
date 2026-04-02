(function () {
  const session = window.CommentLabSession;
  const primaryAction = document.getElementById('menu-primary-action');
  const secondaryAction = document.getElementById('menu-secondary-action');
  const signupTileLink = document.getElementById('signup-tile-link');
  const signupTileDescription = document.getElementById('signup-tile-description');

  function configureAction(listItem, href, label) {
    if (!listItem) {
      return null;
    }

    const link = listItem.querySelector('a');
    if (!link) {
      return null;
    }

    link.href = href;
    link.textContent = label;
    link.removeAttribute('id');
    return link;
  }

  function renderLoggedOutState() {
    configureAction(primaryAction, '/signup', 'Sign Up');
    configureAction(secondaryAction, '/login', 'Log In');
  }

  async function handleLogout(event) {
    event.preventDefault();

    try {
      const response = await session.fetchWithCsrf('/logout', { method: 'POST' });
      if (response.ok) {
        session.clearSessionCookies();
        window.location.replace('/');
      }
    } catch (error) {
      console.error('Failed to log out from menu:', error);
    }
  }

  function renderLoggedInState(username) {
    configureAction(primaryAction, '/account', 'Account');
    const logoutLink = configureAction(secondaryAction, '#', 'Log Out');
    if (logoutLink) {
      logoutLink.addEventListener('click', handleLogout);
    }

    if (signupTileLink) {
      signupTileLink.href = '/account';
      signupTileLink.textContent = 'Account';
    }
    if (signupTileDescription) {
      signupTileDescription.textContent = `Manage credentials, clear Instagram cookies, review account state, and update security settings for ${username}.`;
    }
  }

  async function syncMenu() {
    renderLoggedOutState();

    if (!session) {
      return;
    }

    try {
      const response = await session.fetchWithCsrf('/user-info', {
        method: 'GET',
        headers: { Accept: 'application/json' },
      });

      if (!response.ok) {
        return;
      }

      const payload = await response.json().catch(() => ({}));
      if (!payload.username) {
        return;
      }

      renderLoggedInState(payload.username);
    } catch (error) {
      console.error('Failed to sync menu auth state:', error);
    }
  }

  syncMenu();
})();
