const _loginForm = document.getElementById('login-form');
const _mfaField = document.getElementById('mfa-field');
const _totpInput = document.getElementById('totp_code');
const _orgField = document.getElementById('org-field');
const _orgSelect = document.getElementById('organization_id');

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
  if (_orgField.style.display !== 'none' && !(_orgSelect.value || '').trim()) {
    _orgSelect.focus();
    return;
  }

  try {
    const res = await fetch('/web/login', { method: 'POST', body });
    if (res.ok) { window.location.href = '/'; return; }

    const data = await res.json().catch(() => ({}));
    const detailRaw = data && data.detail;
    const detail = detailRaw && typeof detailRaw === 'object' ? detailRaw : {};
    const detailText = typeof detailRaw === 'string' ? detailRaw : '';
    const mfaRequired =
      res.headers.get('X-MFA-Required') === 'true' ||
      detailText.toLowerCase().includes('mfa code required');

    if (mfaRequired) {
      _mfaField.style.display = '';
      _totpInput.required = true;
      _totpInput.focus();
      _showLoginError('Enter the 6-digit code from your authenticator app.');
      return;
    }
    const orgSelectionRequired = detail && detail.code === 'org_selection_required' && Array.isArray(detail.organizations);
    if (orgSelectionRequired) {
      _orgSelect.innerHTML = '';
      detail.organizations.forEach((org) => {
        const opt = document.createElement('option');
        opt.value = String(org.id);
        const role = org.role ? ` (${String(org.role)})` : '';
        opt.textContent = `${String(org.name)}${role}`;
        _orgSelect.appendChild(opt);
      });
      _orgField.style.display = '';
      _orgSelect.required = true;
      if (_orgSelect.options.length > 0) {
        _orgSelect.value = _orgSelect.options[0].value;
      }
      _showLoginError('Select an organization and sign in again.');
      return;
    }

    // Reset MFA field on wrong-password or other errors
    _mfaField.style.display = 'none';
    _totpInput.required = false;
    _totpInput.value = '';
    _orgField.style.display = 'none';
    _orgSelect.required = false;
    _orgSelect.innerHTML = '';
    _showLoginError(detailText || 'Invalid email or password.');
  } catch (_e) {
    _showLoginError('Network error. Please try again.');
  }
});
