(function () {
  const session = window.CommentLabSession;
  const statusNode = document.getElementById('account-status');

  function setStatus(message, isError = false) {
    if (!statusNode) {
      return;
    }
    statusNode.textContent = message || '';
    statusNode.className = `account-status ${message ? (isError ? 'is-error' : 'is-success') : ''}`.trim();
  }

  function formatDate(value) {
    if (!value) {
      return 'Not available';
    }
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) {
      return value;
    }
    return parsed.toLocaleString();
  }

  function populateAccount(payload) {
    const profile = payload.profile || {};
    const stats = payload.stats || {};

    document.getElementById('profile-username').textContent = profile.username || 'Unknown';
    document.getElementById('profile-email').textContent = profile.email || 'Not set';
    document.getElementById('verification-email-display').textContent = profile.email || 'Not set';
    document.getElementById('profile-email-verified').textContent = profile.email_verified
      ? `Verified at ${formatDate(profile.email_verified_at)}`
      : 'Not verified';
    document.getElementById('profile-instagram-login').textContent = profile.instagram_login || 'Not configured';
    document.getElementById('profile-cookie-state').textContent = profile.has_instagram_cookies
      ? `Stored session from ${formatDate(profile.instagram_cookies_updated_at)}`
      : 'No stored Instagram session';

    document.getElementById('instagram-login').value = profile.instagram_login || '';
    document.getElementById('stat-total-comments').textContent = stats.total_comments || 0;
    document.getElementById('stat-distinct-pages').textContent = stats.distinct_pages || 0;
    document.getElementById('stat-enriched-comments').textContent = stats.enriched_comments || 0;
  }

  async function loadAccount() {
    const response = await session.fetchWithCsrf('/api/account', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    const safeResponse = await session.ensureAuthenticatedResponse(response, '/account');
    if (!safeResponse) {
      return;
    }
    const payload = await safeResponse.json();
    if (!safeResponse.ok) {
      setStatus(payload.error || 'Failed to load account.', true);
      return;
    }
    populateAccount(payload);
  }

  async function submitJson(url, options, successMessage) {
    setStatus('');
    const response = await session.fetchWithCsrf(url, options);
    const safeResponse = await session.ensureAuthenticatedResponse(response, '/account');
    if (!safeResponse) {
      return false;
    }
    const payload = await safeResponse.json();
    if (!safeResponse.ok) {
      setStatus(payload.error || 'Request failed.', true);
      return false;
    }
    setStatus(payload.message || successMessage || 'Saved.');
    await loadAccount();
    return true;
  }

  document.getElementById('password-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const currentPassword = document.getElementById('current-password').value;
    const newPassword = document.getElementById('new-password').value;
    const ok = await submitJson(
      '/api/account/change-password',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      },
      'Password updated successfully.'
    );
    if (ok) {
      event.target.reset();
    }
  });

  document.getElementById('verify-email-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const currentPassword = document.getElementById('verify-email-password').value;
    const ok = await submitJson(
      '/api/account/verify-email',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify({
          current_password: currentPassword,
        }),
      },
      'Email marked as verified.'
    );
    if (ok) {
      event.target.reset();
    }
  });

  document.getElementById('instagram-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const instagramLogin = document.getElementById('instagram-login').value.trim();
    const instagramPassword = document.getElementById('instagram-password').value;
    const ok = await submitJson(
      '/api/account/instagram-credentials',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Accept: 'application/json',
        },
        body: JSON.stringify({
          instagram_login: instagramLogin,
          instagram_password: instagramPassword,
        }),
      },
      'Instagram credentials updated.'
    );
    if (ok) {
      document.getElementById('instagram-password').value = '';
    }
  });

  document.getElementById('delete-instagram-credentials').addEventListener('click', async () => {
    await submitJson(
      '/api/account/instagram-credentials',
      {
        method: 'DELETE',
        headers: {
          Accept: 'application/json',
        },
      },
      'Instagram credentials deleted.'
    );
  });

  document.getElementById('clear-instagram-cookies').addEventListener('click', async () => {
    await submitJson(
      '/api/account/instagram-cookies/clear',
      {
        method: 'POST',
        headers: {
          Accept: 'application/json',
        },
      },
      'Stored Instagram cookies cleared.'
    );
  });

  loadAccount().catch((error) => {
    console.error(error);
    setStatus('Failed to load account.', true);
  });
})();
