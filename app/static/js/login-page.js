const _loginForm = document.getElementById('login-form');
const _mfaField = document.getElementById('mfa-field');
const _totpInput = document.getElementById('totp_code');

function _showLoginError(msg) {
  let err = document.querySelector('.error');
  if (!err) { err = document.createElement('div'); err.className = 'error'; _loginForm.prepend(err); }
  err.textContent = msg;
}

_loginForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = new FormData(_loginForm);

  // If MFA field is visible but empty, focus it and halt
  if (_mfaField.style.display !== 'none' && !(_totpInput.value || '').trim()) {
    _totpInput.focus();
    return;
  }

  try {
    const res = await fetch('/web/login', { method: 'POST', body });
    if (res.ok) { window.location.href = '/'; return; }

    const data = await res.json().catch(() => ({}));
    const mfaRequired =
      res.headers.get('X-MFA-Required') === 'true' ||
      (data.detail || '').toLowerCase().includes('mfa code required');

    if (mfaRequired) {
      _mfaField.style.display = '';
      _totpInput.required = true;
      _totpInput.focus();
      _showLoginError('Enter the 6-digit code from your authenticator app.');
      return;
    }

    // Reset MFA field on wrong-password or other errors
    _mfaField.style.display = 'none';
    _totpInput.required = false;
    _totpInput.value = '';
    _showLoginError(data.detail || 'Invalid email or password.');
  } catch (_e) {
    _showLoginError('Network error. Please try again.');
  }
});
