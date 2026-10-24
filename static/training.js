'use strict';
// C01-C03: deliberate content mistakes, included only for TRAINING_BUGS=1.
// Mutate the existing status dictionary before the first authenticated render.
STATUS.COMPLETED = 'Đang xử lý';

(() => {
  function applyContentMistakes() {
    const uploadHelp = document.querySelector('#create-form .help');
    if (uploadHelp && uploadHelp.dataset.contentBug !== 'C02') {
      uploadHelp.textContent = 'Tối đa 3 tệp, 50 MB/tệp. PDF, PNG, JPG hoặc TXT.';
      uploadHelp.dataset.contentBug = 'C02';
    }
    document.querySelectorAll('#main table tbody td:nth-child(4)').forEach(cell => {
      if (cell.dataset.contentBug === 'C03') return;
      const node = [...cell.childNodes].find(child => child.nodeType === Node.TEXT_NODE && /\d{2}\/\d{2}\/\d{4}/.test(child.textContent));
      if (!node) return;
      cell.dataset.contentBug = 'C03';
      node.textContent = node.textContent.replace(/(\d{2})\/(\d{2})\/(\d{4})/, '$2/$1/$3');
    });
  }
  applyContentMistakes();
  const main = document.querySelector('#main');
  if (main) new MutationObserver(applyContentMistakes).observe(main, {childList: true, subtree: true});
})();
