document.getElementById('login-form').addEventListener('submit', async (e) => {
      e.preventDefault();
      const form = e.target;
      const body = new FormData(form);
      try {
        const res = await fetch('/web/login', { method: 'POST', body });
        if (res.ok) { window.location.href = '/'; return; }
        const data = await res.json().catch(() => ({}));
        let msg = data.detail || 'Invalid email or password.';
        let err = document.querySelector('.error');
        if (!err) { err = document.createElement('div'); err.className = 'error'; form.prepend(err); }
        err.textContent = msg;
      } catch (_e) {
        let err = document.querySelector('.error');
        if (!err) { err = document.createElement('div'); err.className = 'error'; form.prepend(err); }
        err.textContent = 'Network error. Please try again.';
      }
    });
