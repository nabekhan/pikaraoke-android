/* Spatial focus for the TV's D-pad. Ordinary phone browsers keep native input. */
(() => {
  if (!navigator.userAgent.includes('PiKaraokeTV')) return;
  const style = document.createElement('style');
  style.textContent = ':focus-visible{outline:4px solid #55d5c6!important;outline-offset:3px!important}';
  document.head.append(style);
  window.addEventListener('load', () => {
    const connection = typeof socket !== 'undefined' ? socket : window.socket;
    connection?.on('android_network_changed', ({url}) => {
      document.querySelectorAll('.splash-url').forEach(node => {
        const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
          const text = walker.currentNode;
          if (text.textContent.includes('http://')) text.textContent = text.textContent.replace(/http:\/\/[^\s]+/, url);
        }
      });
      document.querySelectorAll('img').forEach(img => {
        if (img.src.includes('/qrcode')) { const src = new URL(img.src); src.searchParams.set('v', Date.now()); img.src = src; }
      });
    });
  });
  const targets = () => [...document.querySelectorAll('a[href],button,input,select,textarea,[tabindex]')]
    .filter(el => !el.disabled && el.tabIndex >= 0 && el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
  document.addEventListener('keydown', event => {
    const current = document.activeElement;
    if (['INPUT','TEXTAREA','SELECT'].includes(current?.tagName)) return;
    const direction = {ArrowUp:[0,-1],ArrowDown:[0,1],ArrowLeft:[-1,0],ArrowRight:[1,0]}[event.key];
    if (!direction) return;
    const all = targets();
    if (!all.length) return;
    event.preventDefault();
    if (!all.includes(current)) { all[0].focus(); return; }
    const rect = current.getBoundingClientRect(), x=rect.x+rect.width/2, y=rect.y+rect.height/2;
    let best=null, cost=Infinity;
    for (const candidate of all) {
      if (candidate === current) continue;
      const r=candidate.getBoundingClientRect(), dx=r.x+r.width/2-x, dy=r.y+r.height/2-y;
      const forward=dx*direction[0]+dy*direction[1], sideways=Math.abs(dx*direction[1]-dy*direction[0]);
      const score=forward+sideways*3;
      if (forward>2 && score<cost) {best=candidate;cost=score;}
    }
    if(best) {best.focus();best.scrollIntoView({block:'nearest',inline:'nearest'});}
  }, true);
})();
