/**
 * Shared form validation helper for BOS.
 * Use with .form-group, .field-error, .field-success, .error-message, .success-message in shared.css.
 * API: BOS.formValidation.showError(field, message), showSuccess(field, message), clear(field), clearForm(form)
 */
(function () {
  function getGroup(field) {
    if (!field) return null;
    if (field.classList && field.classList.contains('form-group')) return field;
    return field.closest ? field.closest('.form-group') : null;
  }

  function ensureMessageEl(group, className) {
    var el = group.querySelector('.' + className);
    if (el) return el;
    el = document.createElement('span');
    el.className = className;
    el.setAttribute('role', 'alert');
    group.appendChild(el);
    return el;
  }

  function showError(field, message) {
    var group = getGroup(field);
    if (!group) return;
    group.classList.remove('field-success');
    group.classList.add('field-error');
    var successEl = group.querySelector('.success-message');
    if (successEl) successEl.style.display = 'none';
    var errEl = ensureMessageEl(group, 'error-message');
    errEl.textContent = message || '';
    errEl.style.display = message ? 'block' : 'none';
  }

  function showSuccess(field, message) {
    var group = getGroup(field);
    if (!group) return;
    group.classList.remove('field-error');
    group.classList.add('field-success');
    var errEl = group.querySelector('.error-message');
    if (errEl) errEl.style.display = 'none';
    var successEl = ensureMessageEl(group, 'success-message');
    successEl.textContent = message || '';
    successEl.style.display = message ? 'block' : 'none';
  }

  function clear(field) {
    var group = getGroup(field);
    if (!group) return;
    group.classList.remove('field-error', 'field-success');
    var err = group.querySelector('.error-message');
    if (err) { err.textContent = ''; err.style.display = 'none'; }
    var ok = group.querySelector('.success-message');
    if (ok) { ok.textContent = ''; ok.style.display = 'none'; }
  }

  function clearForm(form) {
    if (!form) return;
    var groups = form.querySelectorAll('.form-group');
    groups.forEach(function (g) { clear(g); });
  }

  function setupBlurValidation(input, validate) {
    if (!input || typeof validate !== 'function') return;
    input.addEventListener('blur', function () {
      var value = (input.value || '').trim();
      var result = validate(value, input);
      if (result === true) clear(input);
      else if (typeof result === 'string') showError(input, result);
    });
  }

  var BOS = window.BOS || {};
  BOS.formValidation = {
    showError: showError,
    showSuccess: showSuccess,
    clear: clear,
    clearForm: clearForm,
    setupBlurValidation: setupBlurValidation,
    getGroup: getGroup
  };
  window.BOS = BOS;
})();
