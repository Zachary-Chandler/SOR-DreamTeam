// Draws arrows between boxes. <i class="link" data-from="a" data-to="b"> draws a straight arrow from box a
// to box b. data-via="x,y x,y" adds bend points; a coordinate can be "from"/"to" to reuse that box's center.
function edgePoint(r, tx, ty) {
  const cx = r.x + r.w / 2, cy = r.y + r.h / 2, dx = tx - cx, dy = ty - cy;
  const s = Math.min(Math.abs((r.w / 2) / (dx || 1e-9)), Math.abs((r.h / 2) / (dy || 1e-9)));
  return [cx + dx * s, cy + dy * s];
}
function rect(id) { const e = document.getElementById(id); return { x: e.offsetLeft, y: e.offsetTop, w: e.offsetWidth, h: e.offsetHeight }; }
const center = r => [r.x + r.w / 2, r.y + r.h / 2];
window.addEventListener('load', () => {
  const svg = document.querySelector('svg.links'), NS = 'http://www.w3.org/2000/svg';
  for (const l of document.querySelectorAll('i.link')) {
    const a = rect(l.dataset.from), b = rect(l.dataset.to), ca = center(a), cb = center(b);
    const via = (l.dataset.via || '').trim().split(/\s+/).filter(Boolean).map(p => p.split(',').map((v, i) =>
      v === 'from' ? ca[i] : v === 'to' ? cb[i] : Number(v)));
    const first = via[0] || cb, last = via[via.length - 1] || ca;
    const pts = [edgePoint(a, ...first), ...via, edgePoint(b, ...last)];
    const p = document.createElementNS(NS, 'polyline');
    p.setAttribute('points', pts.map(q => q.join(',')).join(' '));
    p.setAttribute('class', l.className.replace('link', '').trim() || 'solid');
    p.setAttribute('marker-end', 'url(#arrow)');
    svg.append(p);
    if (l.dataset.label) {
      const k = Math.floor((pts.length - 1) / 2), [x1, y1] = pts[k], [x2, y2] = pts[k + 1];
      const t = document.createElementNS(NS, 'text');
      t.setAttribute('x', (x1 + x2) / 2 + 6); t.setAttribute('y', (y1 + y2) / 2 - 6);
      t.textContent = l.dataset.label; svg.append(t);
    }
  }
});
