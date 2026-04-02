(function () {
  const session = window.CommentLabSession;

  async function loadHomeSessionState() {
    const indicator = document.getElementById('login-state-indicator');
    const usernameTarget = document.getElementById('login-state-username');
    const hiddenWhenLoggedIn = [
      document.getElementById('menu-login-action'),
      document.getElementById('hero-login-action'),
      document.getElementById('footer-login-link'),
    ];
    const loginTile = document.getElementById('login-tile');
    const loggedInShortcut = document.getElementById('logged-in-shortcut');

    if (!session || !indicator || !usernameTarget) {
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

      usernameTarget.textContent = payload.username;
      indicator.style.display = 'block';

      hiddenWhenLoggedIn.forEach((element) => {
        if (element) {
          element.style.display = 'none';
        }
      });

      if (loginTile) {
        loginTile.innerHTML = `
          <h3><a href="#" class="link" id="logout-home-link">Log Out</a></h3>
          <p>You are already authenticated. Select this tile to end the current session from the home page.</p>
        `;

        const logoutLink = document.getElementById('logout-home-link');
        if (logoutLink) {
          logoutLink.addEventListener('click', async (event) => {
            event.preventDefault();

            try {
              const logoutResponse = await session.fetchWithCsrf('/logout', {
                method: 'POST',
              });
              if (logoutResponse.ok) {
                session.clearSessionCookies();
                window.location.replace('/');
              }
            } catch (error) {
              console.error('Failed to log out from home tile:', error);
            }
          });
        }
      }

      if (loggedInShortcut) {
        loggedInShortcut.style.display = 'inline-block';
      }
    } catch (error) {
      console.error('Failed to load home session state:', error);
    }
  }

  loadHomeSessionState();
})();
