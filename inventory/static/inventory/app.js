// Confirm dialog for any form marked with data-confirm (used for delete).
document.addEventListener('submit', function (e) {
  var msg = e.target && e.target.dataset && e.target.dataset.confirm;
  if (msg && !window.confirm(msg)) e.preventDefault();
});
