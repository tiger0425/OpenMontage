/* ============================================================
   console-v1 · 零件运行时（DOM 构建 + GSAP 动画时间轴）
   companion: apps/console-remake/specs/design-system.md

   架构：HyperFrames 官方 modular / sub-compositions
   - buildScene(tl, data)：被每一幕的 compositions/<scene>.html 调用，
     只构建/驱动本幕自己的元素（幕内相对时间），timeline 键 = 幕 id
   - buildHost(tl, data)：被宿主 index.html 调用，
     只管宿主级 UI（字幕条、BGM 淡出），timeline 键 = "main"

   契约：同步构建；seek-safe（只用 fromTo）；确定性（无随机/时间源）
   ============================================================ */
(function () {
  'use strict';

  /* ---------------- utils ---------------- */
  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function mdBold(s) {
    return esc(s).replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  }
  function E(tag, cls) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    return n;
  }
  function px(v) { return (v || 0) + 'px'; }

  var COLOR_CLASS = { red: 'red', amber: 'amber', blue: 'blue', cyan: 'cyan', ink: 'ink', dim: 'dim' };

  /* ---------------- element builders ---------------- */
  function buildFrame(e) {
    var n = E('div', 'p p-frame p-frame--' + (e.color || 'neutral'));
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';width:' + px(e.w) + ';height:' + px(e.h) + ';';
    if (e.label) {
      var lab = E('div', 'p-frame__label' + (e.label_pos === 'top-center' ? ' p-frame__label--top-center' : ''));
      lab.innerHTML = esc(e.label);
      n.appendChild(lab);
    }
    return n;
  }

  function buildGrid(e) {
    var gap = e.gap == null ? 6 : e.gap;
    var cell = e.cell == null ? 24 : e.cell;
    var cols = e.cols || 10, rows = e.rows || 1;
    var total = rows * cols;
    var on = Math.round((e.fill == null ? 0 : e.fill) * total);
    var w = cols * cell + (cols - 1) * gap;
    var h = rows * cell + (rows - 1) * gap;
    var fillCls = 'p-grid__cell--' + (e.fill_color || 'red');

    var n = E('div', 'p p-grid');
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';width:' + px(w) + ';height:' + px(h) + ';' +
      'grid-template-columns:repeat(' + cols + ',' + px(cell) + ');gap:' + px(gap) + ';';
    for (var i = 0; i < total; i++) {
      var c = E('div', 'p-grid__cell' + (i < on ? ' ' + fillCls : ''));
      if (i < on) c.setAttribute('data-on', '1');
      n.appendChild(c);
    }
    if (e.label_left) {
      var ll = E('div', 'p-grid__label');
      ll.style.cssText = 'left:0;top:0;color:' + (e.label_left_color === 'ink' ? 'var(--ink)' : 'var(--red)') + ';';
      ll.innerHTML = esc(e.label_left);
      n.appendChild(ll);
    }
    if (e.label_right) {
      var lr = E('div', 'p-grid__label');
      lr.style.cssText = 'right:0;top:0;color:var(--ink-dim);text-align:right;';
      lr.innerHTML = esc(e.label_right);
      n.appendChild(lr);
    }
    if (e.divider && on > 0 && on < total) {
      var col = on % cols;
      if (col > 0) {
        var dv = E('div', 'p-grid__divider');
        dv.style.cssText = 'left:' + px(col * (cell + gap) - gap / 2) + ';top:-14px;height:' + px(h + 28) + ';';
        n.appendChild(dv);
      }
    }
    return n;
  }

  function buildPill(e) {
    var size = e.size || 'md';
    var style = e.style || 'solid';
    var cls = 'p p-pill p-pill--' + size;
    if (style === 'outline') cls += ' p-pill--outline p-pill--' + (e.color || 'red');
    else if (style === 'filled') cls += ' p-pill--filled p-pill--' + (COLOR_CLASS[e.color] || 'ink');
    else cls += ' p-pill--' + (COLOR_CLASS[e.color] || 'ink');
    var n = E('div', cls);
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';';
    n.innerHTML = esc(e.text);
    return n;
  }

  function buildHairline(e) {
    var vert = (e.orientation || 'v') === 'v';
    var n = E('div', 'p p-hairline p-hairline--' + (vert ? 'v' : 'h') +
      (e.strong ? ' p-hairline--strong' : '') + (e.tick ? ' p-hairline--tick' : ''));
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';' +
      (vert ? 'width:1px;height:' + px(e.len) + ';' : 'width:' + px(e.len) + ';height:1px;') +
      'transform-origin:center center;';
    if (e.color === 'red') n.style.background = 'var(--red)';
    if (e.color === 'amber') n.style.background = 'var(--amber)';
    if (e.color === 'blue') n.style.background = 'var(--blue)';
    if (e.color === 'cyan') n.style.background = 'var(--cyan)';
    return n;
  }

  function buildBignum(e) {
    var outer = E('div', 'p');
    outer.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';transform:translate(-50%,-50%);';
    var inner = E('div', 'p-bignum p-bignum--' + (e.color || 'red'));
    inner.style.fontSize = px(e.size || 220);
    var m = /^([0-9]+)(.*)$/.exec(String(e.text || ''));
    var suffix = m ? m[2] : '';
    var val = E('span', 'p-bignum__val');
    val.textContent = e.text;
    inner.appendChild(val);
    if (suffix) {
      var sf = E('span', 'p-bignum__suffix');
      sf.textContent = suffix;
      inner.appendChild(sf);
      val.textContent = m[1];
    }
    if (e.sub) {
      var sb = E('div', 'p-bignum__sub');
      sb.innerHTML = esc(e.sub);
      inner.appendChild(sb);
    }
    outer.appendChild(inner);
    outer._animTarget = inner;
    return outer;
  }

  function buildSlot(e) {
    var h = e.h || 56;
    var n = E('div', 'p p-slot');
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';width:' + px(e.w) + ';height:' + px(h) + ';';
    var ticks = e.ticks || 6, filled = e.filled == null ? 0 : e.filled;
    for (var i = 0; i < ticks; i++) {
      var t = E('div', 'p-slot__tick' + (i < filled ? ' p-slot__tick--on' : ''));
      if (i < filled && e.color) t.className = 'p-slot__tick p-slot__tick--' + e.color;
      if (i < filled) t.setAttribute('data-on', '1');
      n.appendChild(t);
    }
    return n;
  }

  function buildPaper(e) {
    var n = E('div', 'p p-paper');
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';width:' + px(e.w) + ';' +
      (e.h ? 'height:' + px(e.h) + ';' : '') + 'position:absolute;';
    if (e.header) {
      var hd = E('div', 'p-paper__header');
      hd.textContent = e.header;
      n.appendChild(hd);
    }
    var lines = e.lines || [];
    var hlIdx = -1, hlText = null;
    if (typeof e.highlight === 'number') hlIdx = e.highlight;
    else if (typeof e.highlight === 'string') hlText = e.highlight;

    for (var i = 0; i < lines.length; i++) {
      var p = E('p', 'p-paper__line');
      var htmlLine = mdBold(lines[i]);
      if (i === hlIdx) {
        p.innerHTML = '<span class="p-paper__hl" style="display:inline-block;width:100%;box-sizing:border-box;transform-origin:left center;">' + htmlLine + '</span>';
        p.setAttribute('data-hl', 'full');
      } else {
        if (hlText) {
          var needle = esc(hlText);
          var pos = htmlLine.indexOf(needle);
          if (pos >= 0) {
            htmlLine = htmlLine.slice(0, pos) +
              '<span class="p-paper__hl" data-hl="part">' + needle + '</span>' +
              htmlLine.slice(pos + needle.length);
          }
        }
        p.innerHTML = htmlLine;
      }
      n.appendChild(p);
    }
    if (e.footer) {
      var ft = E('div', 'p-paper__footer');
      ft.textContent = e.footer;
      n.appendChild(ft);
    }
    return n;
  }

  function buildToast(e) {
    /* 宽缺省保护：缺 w 会让文字逐字换行（竖排假象）——默认 560，超右缘收口 */
    var w = e.w == null ? 560 : e.w;
    if (e.x + w > 1800) w = Math.max(400, 1800 - e.x);
    var n = E('div', 'p p-toast p-toast--' + (e.accent || 'red'));
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';width:' + px(w) + ';';
    if (e.title) {
      var t = E('div', 'p-toast__title');
      t.textContent = e.title;
      n.appendChild(t);
    }
    if (e.body) {
      var b = E('div', 'p-toast__body');
      b.innerHTML = esc(e.body);
      n.appendChild(b);
    }
    return n;
  }

  function buildPanel(e) {
    var n = E('div', 'p p-panel' + (e.tone ? ' p-panel--' + e.tone : ''));
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';width:' + px(e.w) + ';height:' + px(e.h) + ';';
    return n;
  }

  function buildText(e) {
    var cls = 'p-text';
    if (e.mono) cls += ' p-text--mono';
    if (e.strike) cls += ' p-text--strike';
    if (e.dim) cls += ' p-text--dim';
    if (e.bold) cls += ' p-text--bold';
    var outer = E('div', 'p');
    outer.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';' +
      (e.align === 'center' ? 'transform:translateX(-50%);' : '');
    var n = E('div', cls);
    n.style.cssText = 'font-size:' + px(e.size || 40) + ';' +
      (e.color ? 'color:' + e.color + ';' : '') + 'white-space:nowrap;' +
      (e.align === 'center' ? 'text-align:center;' : '');
    n.innerHTML = esc(e.text);
    if (e.strike) {
      var sl = E('i', 'p-strike-line');
      n.appendChild(sl);
    }
    outer.appendChild(n);
    outer._animTarget = n;
    return outer;
  }

  function buildSource(e) {
    var n = E('div', 'p p-source');
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';';
    n.textContent = e.text;
    return n;
  }

  function buildSeal(e) {
    var outer = E('div', 'p');
    outer.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';';
    var inner = E('div', 'p-seal');
    var size = e.size || 100;
    inner.style.cssText = 'width:' + px(size) + ';height:' + px(size) + ';font-size:' + px(size * 0.4) + ';' +
      'transform:rotate(' + (e.rotate == null ? -6 : e.rotate) + 'deg);';
    inner.textContent = e.text;
    outer.appendChild(inner);
    outer._animTarget = inner;
    return outer;
  }

  function buildArrow(e) {
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'p p-arrow p-arrow--' + (e.color || 'red') + (e.dash ? ' p-arrow--dash' : ''));
    svg.style.cssText = 'left:0;top:0;width:1920px;height:1080px;position:absolute;pointer-events:none;overflow:visible;';
    svg._arrowSpec = e;
    return svg;
  }

  /* ---------------- console-v2 builders（界面零件） ---------------- */
  function tk(v) {
    if (!v) return 'var(--accent)';
    if (v.indexOf('var(') === 0 || v.indexOf('#') === 0 || v.indexOf('rgba') === 0 || v.indexOf('rgb') === 0) return v;
    return 'var(--' + v + ')';
  }

  function buildWin(e) {
    var n = E('div', 'p p-win' + (e.focus ? ' p-win--focus' : ''));
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';width:' + px(e.w) + ';height:' + px(e.h) + ';';
    n.appendChild(E('div', 'p-win__bar'));
    var dots = E('div', 'p-win__dots');
    dots.innerHTML = '<i class="p-win__dot p-win__dot--r"></i>' +
      '<i class="p-win__dot p-win__dot--y"></i><i class="p-win__dot p-win__dot--g"></i>';
    n.appendChild(dots);
    if ((e.kind || 'app') === 'browser') {
      if (e.url) {
        var u = E('div', 'p-win__url');
        u.textContent = e.url;
        n.appendChild(u);
      }
    } else if (e.title) {
      var tt = E('div', 'p-win__title');
      tt.textContent = e.title;
      n.appendChild(tt);
    }
    n._dots = n.querySelectorAll('.p-win__dot');
    n._title = n.querySelector('.p-win__title, .p-win__url');
    return n;
  }

  function buildTerm(e) {
    var n = E('div', 'p p-term');
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';width:' + px(e.w) + ';';
    var cmd = e.cmd || '';
    if (cmd) {
      var row = E('div', 'p-term__cmd');
      var pr = E('span', 'p-term__prompt');
      pr.textContent = e.prompt == null ? '\u276f' : e.prompt;
      var ct = E('span', 'p-term__cmdtext');
      var html = '';
      for (var i = 0; i < cmd.length; i++) {
        var ch = cmd.charAt(i);
        html += '<span class="tc">' + (ch === ' ' ? '&nbsp;' : esc(ch)) + '</span>';
      }
      ct.innerHTML = html;
      row.appendChild(pr);
      row.appendChild(ct);
      row.appendChild(E('i', 'p-term__cursor'));
      n.appendChild(row);
      n._chars = ct.querySelectorAll('.tc');
    }
    var outs = [];
    (e.out || []).forEach(function (s) {
      var o = E('div', 'p-term__out');
      o.textContent = s;
      n.appendChild(o);
      outs.push(o);
    });
    n._outs = outs;
    return n;
  }

  function buildRows(e) {
    var card = e.card !== false;
    var n = E('div', 'p p-rows' + (card ? ' p-rows--card' : ''));
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';width:' + px(e.w) + ';' +
      (e.h ? 'height:' + px(e.h) + ';' : '');
    if (e.title) {
      var t = E('div', 'p-rows__title');
      t.textContent = e.title;
      n.appendChild(t);
    }
    var rowH = e.row_h || 56;
    (e.rows || []).forEach(function (r) {
      var row = E('div', 'p-rows__row');
      row.style.height = px(rowH);
      var dot = E('i', 'p-rows__dot' + (r.dot ? ' p-rows__dot--' + r.dot : ''));
      var tx = E('span', 'p-rows__text');
      tx.textContent = r.text || '';
      row.appendChild(dot);
      row.appendChild(tx);
      if (r.tag) {
        var tag = E('span', 'p-rows__tag' + (r.tag_tone ? ' p-rows__tag--' + r.tag_tone : ''));
        tag.textContent = r.tag;
        row.appendChild(tag);
      }
      n.appendChild(row);
    });
    n._rows = n.querySelectorAll('.p-rows__row');
    n._dots = n.querySelectorAll('.p-rows__dot');
    return n;
  }

  function buildRepoCard(e) {
    var n = E('div', 'p p-repocard' + (e.tone === 'accent' ? ' p-repocard--accent' : ''));
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';width:' + px(e.w) + ';' +
      (e.h ? 'height:' + px(e.h) + ';' : '');
    var g = E('div', 'p-repocard__glyph');
    g.innerHTML = '<i class="g-bar"></i><i class="g-bar g-bar--2"></i><i class="g-dot"></i>';
    n.appendChild(g);
    var body = E('div', 'p-repocard__body');
    var name = E('div', 'p-repocard__name');
    name.textContent = e.name || '';
    body.appendChild(name);
    if (e.desc) {
      var d = E('div', 'p-repocard__desc');
      d.textContent = e.desc;
      body.appendChild(d);
    }
    var meta = E('div', 'p-repocard__meta');
    var mh = '';
    if (e.lang) {
      mh += '<i class="p-repocard__langdot" style="background:' + tk(e.lang_color || 'accent') + '"></i>' +
        '<span class="p-repocard__lang">' + esc(e.lang) + '</span>';
    }
    if (e.stars) mh += '<span class="p-repocard__stars">\u2605 ' + esc(e.stars) + '</span>';
    meta.innerHTML = mh;
    body.appendChild(meta);
    n.appendChild(body);
    if (e.badge) {
      var b = E('div', 'p-repocard__badge');
      b.textContent = e.badge;
      n.appendChild(b);
    }
    n._meta = meta;
    n._badge = n.querySelector('.p-repocard__badge');
    return n;
  }

  function buildMark(e) {
    var kind = e.kind || 'hl';
    var n = E('div', 'p p-mark p-mark--' + kind + ' p-mark--' + (e.color || 'amber'));
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';width:' + px(e.w) + ';height:' + px(e.h) + ';' +
      (e.rot ? 'transform:rotate(' + e.rot + 'deg);' : '');
    if (kind === 'cross') {
      /* 两条线按框对角线拟合（长宽自适应，不溢出） */
      var w = e.w || 0, h = e.h || 0;
      var len = Math.round(Math.sqrt(w * w + h * h));
      var ang = Math.atan2(h, w) * 180 / Math.PI;
      var mkLine = function (deg) {
        var s = E('i', 'p-mark__x');
        s.style.cssText = 'position:absolute;left:' + ((w - len) / 2) + 'px;top:50%;width:' + len + 'px;height:3px;' +
          'margin-top:-1.5px;transform-origin:center center;transform:rotate(' + deg + 'deg);';
        return s;
      };
      n.appendChild(mkLine(ang));
      n.appendChild(mkLine(-ang));
      n._xlines = n.querySelectorAll('.p-mark__x');
    }
    return n;
  }

  function buildBars(e) {
    var n = E('div', 'p p-bars');
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';width:' + px(e.w) + ';';
    var lw = e.label_w == null ? 200 : e.label_w;
    var vw = e.value_w == null ? 150 : e.value_w;
    var bh = e.bar_h == null ? 26 : e.bar_h;
    var gap = e.gap == null ? 26 : e.gap;
    var fills = [];
    (e.rows || []).forEach(function (r) {
      var row = E('div', 'p-bars__row');
      row.style.cssText = 'height:' + px(bh) + ';margin-bottom:' + px(gap) + ';';
      var lab = E('span', 'p-bars__label');
      lab.style.width = px(lw);
      lab.textContent = r.label || '';
      var track = E('div', 'p-bars__track');
      track.style.height = px(bh);
      var fill = E('i', 'p-bars__fill p-bars__fill--' + (r.color || 'accent'));
      fill.style.cssText = 'height:' + px(bh) + ';width:' + (Math.max(0, Math.min(1, r.value)) * 100).toFixed(2) + '%;';
      fills.push(fill);
      track.appendChild(fill);
      var val = E('span', 'p-bars__value');
      val.style.width = px(vw);
      val.textContent = r.text != null ? r.text : String(r.value);
      row.appendChild(lab);
      row.appendChild(track);
      row.appendChild(val);
      n.appendChild(row);
    });
    n._fills = fills;
    return n;
  }

  function buildShape(e) {
    var n = E('div', 'p p-shape' + (e.stage3d ? ' p-shape--3d' : ''));
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';width:' + px(e.w || 1) + ';height:' + px(e.h || 1) + ';';
    var host = n;
    if (e.stage3d) {
      host = E('div', 'p-shape__stage');
      n.appendChild(host);
    }
    var groups = {};
    (e.prims || []).forEach(function (p) {
      var d = E('div', 'p-shape__prim' + (p.kind === 'circle' ? ' p-shape__prim--circle' : ''));
      var css = '';
      var pw = p.w || 16, ph = p.h || 16;
      if (e.stage3d) {
        /* 3D 模式：prims 以 stage 中心为原点 (x 右 / y 下 / z 朝外)，
           transform 顺序 = 平移到位 → 绕自身中心旋转 */
        var tx = (p.x || 0) - pw / 2;
        var ty = (p.y || 0) - ph / 2;
        css += 'left:50%;top:50%;width:' + px(pw) + ';height:' + px(ph) + ';' +
          'transform:translate3d(' + tx + 'px,' + ty + 'px,' + (p.z || 0) + 'px)' +
          ' rotateX(' + (p.rx || 0) + 'deg) rotateY(' + (p.ry || 0) + 'deg) rotateZ(' + (p.rz || 0) + 'deg);';
      } else {
        css += 'left:' + px(p.x || 0) + ';top:' + px(p.y || 0) + ';width:' + px(pw) + ';height:' + px(ph) + ';';
        if (p.rot) css += 'transform:rotate(' + p.rot + 'deg);';
      }
      if (p.r != null) css += 'border-radius:' + px(p.r) + ';';
      if (p.fill) {
        css += 'background:' + tk(p.color) + ';border:none;';
      } else {
        css += 'border:' + px(p.border == null ? 2 : p.border) + ' solid ' + tk(p.color || 'rgba(255,255,255,0.5)') + ';box-sizing:border-box;';
      }
      if (p.op != null) css += 'opacity:' + p.op + ';';
      d.style.cssText = css;
      var st = p.stage || 1;
      (groups[st] = groups[st] || []).push(d);
      host.appendChild(d);
    });
    if (e.stage3d) {
      host.style.transform = 'rotateX(' + (e.rot_x == null ? -14 : e.rot_x) + 'deg)' +
        ' rotateY(' + (e.spin_from != null ? e.spin_from : (e.rot_y == null ? -18 : e.rot_y)) + 'deg)';
    }
    var stages = [];
    Object.keys(groups).sort(function (a, b) { return a - b; }).forEach(function (k) { stages.push(groups[k]); });
    n._stages = stages;
    n._3dstage = e.stage3d ? host : null;
    return n;
  }


  /* ---------------- connectors: arrow / leader / bracket ----------------
     leader 引线：把标签系到元素（默认 from=bottom → to=top，带端刻度）
     bracket 括线：把一组元素横向括起（x1..x2 at y，端部下折）
     端点是延迟测量的（与箭头共用同一套重测机制） */
  /* console-v2.2 · 真实图片素材（image 零件）：真实照片/官方图/截帧放进窗口框 */
  function buildImage(e) {
    var n = E('div', 'p p-photo' + (e.dim ? ' p-photo--dim' : '') + (e.bare ? ' p-photo--bare' : ''));
    n.style.cssText = 'left:' + px(e.x) + ';top:' + px(e.y) + ';width:' + px(e.w) + ';height:' + px(e.h) + ';' +
      (e.radius != null ? 'border-radius:' + px(e.radius) + ';' : '');
    var img = E('img', 'p-photo__img');
    img.src = 'assets/images/' + e.src;
    img.alt = e.label || '';
    img.style.objectFit = e.fit || 'cover';
    if (e.grading) img.setAttribute('data-color-grading', JSON.stringify(e.grading));
    n.appendChild(img);
    if (e.label) {
      var lab = E('div', 'p-photo__label');
      lab.innerHTML = esc(e.label);
      n.appendChild(lab);
    }
    return n;
  }

  function buildConnector(e) {
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    var cls = 'p p-arrow p-arrow--' + (e.color || (e.type === 'leader' ? 'ink' : 'red')) +
      (e.dash ? ' p-arrow--dash' : '');
    svg.setAttribute('class', cls);
    svg.style.cssText = 'left:0;top:0;width:1920px;height:1080px;position:absolute;pointer-events:none;overflow:visible;';
    svg._connSpec = e;
    e.type = e.type; /* keep */
    return svg;
  }

  function _endpoint(el, side, defSide, ox, oy) {
    var s = side || defSide;
    var sp = el._spec || {};
    var bx, by, bw, bh;
    el._usedDom = false;
    if (typeof sp.x === 'number' && typeof sp.y === 'number' &&
        typeof sp.w === 'number' && typeof sp.h === 'number') {
      /* 优先用分幕坐标（确定几何，渲染器布局未就绪时也稳定） */
      bx = sp.x; by = sp.y; bw = sp.w; bh = sp.h;
    } else {
      var r = el.getBoundingClientRect();
      bx = r.left - ox; by = r.top - oy; bw = r.width; bh = r.height;
      el._usedDom = true;
    }
    var x = bx + bw / 2, y = by + bh / 2;
    if (s === 'left') x = bx;
    else if (s === 'right') x = bx + bw;
    else if (s === 'top') y = by;
    else if (s === 'bottom') y = by + bh;
    return { x: x, y: y };
  }

  function resolveConnector(svg, byId, origin) {
    var e = svg._connSpec;
    var kind = e.type;
    var ox = origin ? origin.left : 0;
    var oy = origin ? origin.top : 0;

    var p1, p2;
    var defFrom = kind === 'leader' ? 'bottom' : 'right';
    var defTo = kind === 'leader' ? 'top' : 'left';
    if (e.from && byId[e.from]) p1 = _endpoint(byId[e.from], e.from_side, defFrom, ox, oy);
    else p1 = { x: e.x1, y: e.y1 };
    if (e.to && byId[e.to]) p2 = _endpoint(byId[e.to], e.to_side, defTo, ox, oy);
    else if (kind === 'bracket') p2 = { x: e.x2, y: (e.y != null ? e.y : e.y2) };
    else p2 = { x: e.x2, y: e.y2 };
    svg._needsLayout = !!(byId[e.from] && byId[e.from]._usedDom) || !!(byId[e.to] && byId[e.to]._usedDom);

    var line = svg._line;
    var head = svg._head;
    if (!line) {
      line = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      line.setAttribute('stroke', 'currentColor');
      line.setAttribute('stroke-dasharray', '99999');
      line.setAttribute('stroke-dashoffset', '99999');
      svg.appendChild(line);
      svg._line = line;
      if (kind === 'arrow') {
        head = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        head.setAttribute('fill', 'currentColor');
        head.setAttribute('stroke', 'none');
        head.setAttribute('data-head', '1');
        svg.appendChild(head);
        svg._head = head;
      }
      svg.style.opacity = '0';
    }

    var d = '';
    var dx = p2.x - p1.x, dy = p2.y - p1.y;
    var len = Math.sqrt(dx * dx + dy * dy) || 1;
    var ux = dx / len, uy = dy / len;
    var px = -uy, py = ux; /* 垂直单位向量 */

    if (kind === 'arrow') {
      var pad = e.pad == null ? 10 : e.pad;
      var sx = p1.x + ux * pad, sy = p1.y + uy * pad;
      var ex = p2.x - ux * pad, ey = p2.y - uy * pad;
      d = 'M' + sx + ' ' + sy + 'L' + ex + ' ' + ey;
      var ah = 13;
      var bx = ex - ux * ah, by = ey - uy * ah;
      if (head) {
        head.setAttribute('d', 'M' + ex + ' ' + ey +
          'L' + (bx + px * ah * 0.62) + ' ' + (by + py * ah * 0.62) +
          'L' + (bx - px * ah * 0.62) + ' ' + (by - py * ah * 0.62) + 'Z');
      }
    } else if (kind === 'bracket') {
      var y = p1.y;
      var tickLen = e.tick_len == null ? 9 : e.tick_len;
      var dir = e.up ? -1 : 1;
      d = 'M' + p1.x + ' ' + y + 'L' + p2.x + ' ' + y +
        'M' + p1.x + ' ' + y + 'l0 ' + (tickLen * dir) +
        'M' + p2.x + ' ' + y + 'l0 ' + (tickLen * dir);
    } else {
      /* leader：直线 + 可选端刻度 */
      d = 'M' + p1.x + ' ' + p1.y + 'L' + p2.x + ' ' + p2.y;
      if (e.tick !== false) {
        var tl = e.tick_len == null ? 3.5 : e.tick_len;
        d += 'M' + (p1.x - px * tl) + ' ' + (p1.y - py * tl) + 'L' + (p1.x + px * tl) + ' ' + (p1.y + py * tl);
        d += 'M' + (p2.x - px * tl) + ' ' + (p2.y - py * tl) + 'L' + (p2.x + px * tl) + ' ' + (p2.y + py * tl);
      }
    }
    line.setAttribute('d', d);
    try { svg._lineLen = line.getTotalLength(); } catch (err) { svg._lineLen = len + 20; }
    return svg;
  }

  /* 把 dash 状态按 drawProgress(0..1) 写到当前几何上 */
  function paintArrow(svg, progress) {
    var line = svg._line;
    if (!line) return;
    var L = svg._lineLen || 0;
    line.setAttribute('stroke-dasharray', String(L));
    line.setAttribute('stroke-dashoffset', String(L * (1 - progress)));
  }

  /* ---------------- animation per element ---------------- */
  function animElement(tl, node, e, t) {
    var inner = node._animTarget;
    var target = inner || node;

    /* ---- 动作动效（motion）：把台词里的动词演出来 ---- */
    if (e.motion === 'travel') {
      /* 行进：从偏移位置滑入落位（跑/走过/拉进来） */
      tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: 0.22 }, t);
      tl.fromTo(target, { x: e.mdx || 0, y: e.mdy || 0 },
        { x: 0, y: 0, duration: e.motion_dur || 0.85, ease: e.motion_ease || 'power2.out' }, t);
      if (e.travel_fade) tl.to(node, { opacity: 0, duration: 0.3 }, t + (e.motion_dur || 0.85) - 0.05);
      return;
    }
    if (e.motion === 'stack') {
      /* 层叠：从下方叠上来落定（叠/压/盖） */
      tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: 0.28 }, t);
      tl.fromTo(target, { y: e.mdy == null ? 24 : e.mdy, scale: 0.985 },
        { y: 0, scale: 1, duration: e.motion_dur || 0.6, ease: 'power3.out' }, t);
      return;
    }
    if (e.motion === 'grow') {
      /* 生长：从左向右长出（变长/张开/铺开） */
      node.style.transformOrigin = 'left center';
      tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: 0.18 }, t);
      tl.fromTo(target, { scaleX: 0 }, { scaleX: 1, duration: e.motion_dur || 0.7, ease: 'power3.out' }, t);
      return;
    }
    if (e.motion === 'push') {
      /* 塞入：先正常显形，随后被推入目标处并缩小消失（塞给/灌进） */
      var pd = e.motion_dur || 0.7;
      var pat = t + (e.push_at == null ? 1.6 : e.push_at);
      tl.to(target, { x: e.mdx || 0, y: e.mdy || 0, scale: e.push_scale == null ? 0.12 : e.push_scale,
        duration: pd, ease: 'power2.in' }, pat);
      tl.to(node, { opacity: 0, duration: 0.25 }, pat + pd - 0.22);
    }
    if (e.motion === 'shift') {
      /* 位移：在句中向一侧挪动（挪/移/推走） */
      tl.to(target, { x: e.mdx || 0, y: e.mdy || 0, duration: e.motion_dur || 0.6,
        ease: 'power2.inOut' }, t + (e.shift_at == null ? 0.9 : e.shift_at));
    }
    if (e.motion === 'erase') {
      /* 擦除：显形后被划掉（删/失效/不存在） */
      node.style.transformOrigin = 'left center';
      var eat = t + (e.erase_at == null ? 1.4 : e.erase_at);
      tl.to(node, { opacity: 0, scaleX: 0.15, duration: 0.5, ease: 'power2.in' }, eat);
    }
    if (e.motion === 'reject') {
      /* 弹回：尝试靠近 → 撞上被弹开 → 坠落淡出（打不开/够不到/被拦住） */
      var ad = e.approach_dur == null ? 0.42 : e.approach_dur;
      var bd = e.bounce_dur == null ? 0.32 : e.bounce_dur;
      var fd = e.fall_dur == null ? 0.5 : e.fall_dur;
      var t0 = t + (e.reject_at == null ? 0.2 : e.reject_at);
      tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: 0.18 }, t);
      tl.fromTo(target, { x: 0, y: 0 }, { x: e.mdx || 0, y: e.mdy || 0, duration: ad, ease: 'power2.in' }, t0);
      tl.to(target, { x: (e.mdx || 0) * 0.32, y: (e.mdy || 0) * 0.32, duration: bd, ease: 'power2.out' }, t0 + ad);
      tl.to(target, { y: (e.mdy || 0) * 0.32 + 72, duration: fd, ease: 'power1.in' }, t0 + ad + bd);
      tl.to(node, { opacity: 0, duration: fd * 0.8 }, t0 + ad + bd + fd * 0.25);
    }
    if (e.motion === 'leak') {
      /* 泄漏：底部渗出小方块落下（漏/掉/流失） */
      var n = e.leak_n || 6;
      for (var li = 0; li < n; li++) {
        (function (i) {
          var dot = E('div', 'p-leak-dot');
          dot.style.left = (8 + i * (84 / n)) + '%';
          node.appendChild(dot);
          var st = t + (e.leak_at == null ? 0.6 : e.leak_at) + i * (e.leak_gap == null ? 0.14 : e.leak_gap);
          tl.fromTo(dot, { opacity: 0, y: 0 }, { opacity: 1, duration: 0.12 }, st);
          tl.to(dot, { y: e.leak_dy == null ? 92 : e.leak_dy, opacity: 0, duration: 0.7, ease: 'power1.in' }, st + 0.1);
        })(li);
      }
    }

    if (e.type === 'win') {
      tl.fromTo(node, { opacity: 0, y: e.enter_from === 'top' ? -12 : 14, scale: 0.988 },
        { opacity: 1, y: 0, scale: 1, duration: 0.5, ease: 'power3.out' }, t);
      if (node._dots && node._dots.length) {
        tl.fromTo(node._dots, { scale: 0.4, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.24, stagger: 0.06, ease: 'back.out(2)' }, t + 0.22);
      }
      if (node._title) {
        tl.fromTo(node._title, { opacity: 0 }, { opacity: 1, duration: 0.3 }, t + 0.3);
      }
      return;
    }
    if (e.type === 'term') {
      tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: 0.22 }, t);
      var tchars = node._chars || [];
      var tspeed = e.type_speed == null ? 0.028 : e.type_speed;
      if (tchars && tchars.length) {
        tl.fromTo(tchars, { opacity: 0 }, { opacity: 1, duration: 0.012, stagger: tspeed, ease: 'none' }, t + 0.12);
      }
      var tcur = node.querySelector('.p-term__cursor');
      if (tcur) {
        tl.fromTo(tcur, { opacity: 0 }, { opacity: 0.9, duration: 0.18 }, t + 0.12 + (tchars ? tchars.length : 0) * tspeed * 0.45);
      }
      var outs = node._outs || [];
      if (outs.length) {
        tl.fromTo(outs, { opacity: 0, y: 6 }, { opacity: 1, y: 0, duration: 0.3, stagger: e.out_stagger == null ? 0.16 : e.out_stagger, ease: 'power2.out' }, t + 0.55 + (tchars ? tchars.length : 0) * tspeed);
      }
      return;
    }
    if (e.type === 'rows') {
      tl.fromTo(node, { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out' }, t);
      var rrows = node._rows || [];
      var rdots = node._dots || [];
      var rst = e.stagger == null ? 0.12 : e.stagger;
      if (rrows.length) {
        tl.fromTo(rrows, { opacity: 0, x: -8 }, { opacity: 1, x: 0, duration: 0.32, stagger: rst, ease: 'power2.out' }, t + 0.2);
      }
      if (rdots.length) {
        tl.fromTo(rdots, { scale: 0.3, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.22, stagger: rst, ease: 'back.out(2.4)' }, t + 0.42);
      }
      return;
    }
    if (e.type === 'repocard') {
      tl.fromTo(node, { opacity: 0, y: 16, scale: 0.985 },
        { opacity: 1, y: 0, scale: 1, duration: 0.5, ease: 'power3.out' }, t);
      if (node._meta) tl.fromTo(node._meta, { opacity: 0 }, { opacity: 1, duration: 0.3 }, t + 0.25);
      if (node._badge) tl.fromTo(node._badge, { opacity: 0, scale: 1.4 }, { opacity: 1, scale: 1, duration: 0.32, ease: 'back.out(2)' }, t + 0.4);
      return;
    }
    if (e.type === 'mark') {
      var mk = e.kind || 'hl';
      if (mk === 'hl') {
        node.style.transformOrigin = 'left center';
        tl.fromTo(node, { opacity: 0, scaleX: 0.1 }, { opacity: 1, scaleX: 1, duration: 0.4, ease: 'power2.out' }, t);
      } else if (mk === 'ul') {
        tl.fromTo(node, { opacity: 0, scaleX: 0 }, { opacity: 1, scaleX: 1, duration: e.draw_dur || 0.45, ease: 'power2.inOut' }, t);
      } else if (mk === 'ring') {
        tl.fromTo(node, { opacity: 0, scale: 1.12 }, { opacity: 1, scale: 1, duration: 0.38, ease: 'power3.out' }, t);
      } else {
        tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: 0.12 }, t);
        var mxs = node._xlines || [];
        if (mxs.length) {
          tl.fromTo(mxs, { scaleX: 0 }, { scaleX: 1, duration: 0.3, stagger: 0.13, ease: 'power2.inOut' }, t + 0.05);
        }
      }
      return;
    }
    if (e.type === 'bars') {
      tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: 0.3 }, t);
      var brows = node.querySelectorAll('.p-bars__row');
      if (brows.length) tl.fromTo(brows, { opacity: 0 }, { opacity: 1, duration: 0.25, stagger: 0.12 }, t + 0.1);
      var bfills = node._fills || [];
      if (bfills.length) {
        tl.fromTo(bfills, { scaleX: 0 }, { scaleX: 1, duration: e.grow_dur || 0.8, stagger: e.stagger == null ? 0.22 : e.stagger, ease: 'power3.out' }, t + 0.2);
      }
      return;
    }
    if (e.type === 'shape') {
      var stages = node._stages || [];
      var sstg = e.stage_stagger == null ? 0.55 : e.stage_stagger;
      tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: 0.01 }, t);
      stages.forEach(function (group, gi) {
        tl.fromTo(group, { opacity: 0, scale: 0.97 },
          { opacity: 1, scale: 1, duration: e.prim_dur || 0.35, stagger: 0.05, ease: 'power2.out' }, t + gi * sstg);
      });
      if (node._3dstage && e.spin_to != null) {
        var spinFrom = e.spin_from == null ? -32 : e.spin_from;
        tl.fromTo(node._3dstage,
          { rotationX: e.rot_x == null ? -14 : e.rot_x, rotationY: spinFrom },
          { rotationY: e.spin_to, duration: e.spin_dur || 6, ease: 'power1.inOut' }, t);
      }
      return;
    }
    if (e.type === 'arrow' || e.type === 'leader' || e.type === 'bracket') {
      var proxy = { p: 0 };
      tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: 0.01 }, t);
      tl.fromTo(proxy, { p: 0 }, {
        p: 1, duration: e.draw_dur || (e.type === 'arrow' ? 0.38 : 0.3), ease: 'power2.inOut',
        onUpdate: function () { paintArrow(node, proxy.p); }
      }, t);
      if (node._head) {
        tl.fromTo(node._head, { opacity: 0 }, { opacity: 1, duration: 0.12 }, t + (e.draw_dur || 0.38) - 0.12);
      }
      return;
    }
    if (e.type === 'grid') {
      tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: 0.3, ease: 'power2.out' }, t);
      var cells = node.querySelectorAll('.p-grid__cell');
      var base = [], onCells = [];
      for (var i = 0; i < cells.length; i++) {
        if (cells[i].getAttribute('data-on')) onCells.push(cells[i]); else base.push(cells[i]);
      }
      tl.fromTo(base, { opacity: 0 }, { opacity: 1, duration: 0.3, stagger: 0.006, ease: 'none' }, t);
      tl.fromTo(onCells, { opacity: 0 }, { opacity: 1, duration: 0.22, stagger: e.stagger == null ? 0.012 : e.stagger, ease: 'none' }, t + 0.25);
      var dv = node.querySelector('.p-grid__divider');
      if (dv) tl.fromTo(dv, { scaleY: 0, opacity: 0 }, { scaleY: 1, opacity: 1, duration: 0.25, ease: 'power2.out' }, t + 0.25 + onCells.length * (e.stagger == null ? 0.012 : e.stagger) + 0.1);
      var labs = node.querySelectorAll('.p-grid__label');
      if (labs.length) tl.fromTo(labs, { opacity: 0 }, { opacity: 1, duration: 0.3 }, t + 0.1);
      return;
    }
    if (e.type === 'paper') {
      tl.fromTo(node, { opacity: 0, y: -14 }, { opacity: 1, y: 0, duration: 0.45, ease: 'power2.out' }, t);
      var lines = node.querySelectorAll('.p-paper__line');
      tl.fromTo(lines, { opacity: 0 }, { opacity: 1, duration: 0.3, stagger: 0.06, ease: 'power1.out' }, t + 0.18);
      var hd = node.querySelector('.p-paper__header');
      if (hd) tl.fromTo(hd, { opacity: 0, y: -6 }, { opacity: 1, y: 0, duration: 0.25, ease: 'power2.out' }, t + 0.4);
      var hlFull = node.querySelector('[data-hl="full"]');
      if (hlFull) tl.fromTo(hlFull, { scaleX: 0, opacity: 0 }, { scaleX: 1, opacity: 1, duration: 0.3, ease: 'power2.inOut' }, t + 0.3 + lines.length * 0.06);
      var hlPart = node.querySelector('[data-hl="part"]');
      if (hlPart) tl.fromTo(hlPart, { opacity: 0 }, { opacity: 1, duration: 0.25 }, t + 0.45);
      var ft = node.querySelector('.p-paper__footer');
      if (ft) tl.fromTo(ft, { opacity: 0 }, { opacity: 1, duration: 0.3 }, t + 0.6);
      return;
    }
    if (e.type === 'bignum') {
      var m = /^([0-9]+)(.*)$/.exec(String(e.text || ''));
      if (e.count && m) {
        var proxy = { v: e.count_from == null ? 0 : e.count_from };
        var valNode = node.querySelector('.p-bignum__val');
        tl.fromTo(proxy, { v: proxy.v }, {
          v: parseFloat(m[1]), duration: e.count_dur || 0.75, ease: 'power2.out',
          onUpdate: function () { valNode.textContent = String(Math.round(proxy.v)); }
        }, t + 0.1);
      }
      tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: 0.4, ease: 'power2.out' }, t);
      tl.fromTo(inner, { scale: 0.94 }, { scale: 1, duration: 0.45, ease: 'power3.out' }, t);
      return;
    }
    if (e.type === 'frame') {
      tl.fromTo(node, { opacity: 0, scale: 0.985 }, { opacity: 1, scale: 1, duration: 0.4, ease: 'power2.out' }, t);
      var lab = node.querySelector('.p-frame__label');
      if (lab) tl.fromTo(lab, { opacity: 0 }, { opacity: 1, duration: 0.25 }, t + 0.18);
      return;
    }
    if (e.type === 'pill') {
      var off = 6;
      var from = { opacity: 0, y: e.enter_from === 'top' ? -off : e.enter_from === 'right' ? 0 : off, x: e.enter_from === 'right' ? off : 0 };
      tl.fromTo(node, from, { opacity: 1, y: 0, x: 0, duration: 0.35, ease: 'power2.out' }, t);
      return;
    }
    if (e.type === 'hairline') {
      var vert = (e.orientation || 'v') === 'v';
      tl.fromTo(node, vert ? { scaleY: 0, opacity: 0 } : { scaleX: 0, opacity: 0 },
        vert ? { scaleY: 1, opacity: 1, duration: 0.25, ease: 'power2.out' } : { scaleX: 1, opacity: 1, duration: 0.25, ease: 'power2.out' }, t);
      return;
    }
    if (e.type === 'slot') {
      tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: 0.3 }, t);
      var ticks = node.querySelectorAll('.p-slot__tick');
      tl.fromTo(ticks, { opacity: 0, scaleY: 0.6 }, { opacity: 1, scaleY: 1, duration: 0.2, stagger: 0.05 }, t + 0.15);
      return;
    }
    if (e.type === 'toast') {
      tl.fromTo(node, { opacity: 0, x: 12 }, { opacity: 1, x: 0, duration: 0.38, ease: 'back.out(1.4)' }, t);
      return;
    }
    if (e.type === 'seal') {
      tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: 0.2, ease: 'power1.out' }, t);
      tl.fromTo(inner, { scale: 1.5 }, { scale: 1, duration: 0.32, ease: 'power3.in' }, t);
      return;
    }
    if (e.type === 'panel') {
      tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: e.fade_dur || 0.45, ease: 'power2.out' }, t);
      return;
    }
    if (e.type === 'image') {
      /* 真实图片：轻微推近 + 淡入（照片不闪切） */
      tl.fromTo(node, { opacity: 0, scale: e.scale_from == null ? 0.985 : e.scale_from, y: 6 },
        { opacity: 1, scale: 1, y: 0, duration: e.in_dur || 0.5, ease: 'power3.out' }, t);
      return;
    }
    /* text / source / fallback */
    if (inner) {
      tl.fromTo(node, { opacity: 0 }, { opacity: 1, duration: 0.38, ease: 'power2.out' }, t);
      tl.fromTo(inner, { y: 8 }, { y: 0, duration: 0.38, ease: 'power2.out' }, t);
      var sl = inner.querySelector ? inner.querySelector('.p-strike-line') : null;
      if (sl) {
        tl.fromTo(sl, { scaleX: 0 }, { scaleX: 1, duration: 0.35, ease: 'power2.inOut' },
          t + (e.strike_at == null ? 0.4 : e.strike_at));
      }
      return;
    }
    tl.fromTo(node, { opacity: 0, y: 8 }, { opacity: 1, y: 0, duration: 0.38, ease: 'power2.out' }, t);
  }

  /* ---------------- scene root resolution ---------------- */
  function resolveSceneRoot(sceneId) {
    var s = document.currentScript;
    if (s && s.closest) {
      var slot = s.closest('[data-composition-src]');
      if (slot) {
        var inner = slot.querySelector('[data-composition-id="' + sceneId + '"]');
        return inner || slot;
      }
    }
    var found = document.querySelector('[data-composition-id="' + sceneId + '"]');
    if (found && found.getAttribute('data-composition-src')) {
      return found.querySelector('[data-composition-id="' + sceneId + '"]') || found;
    }
    return found;
  }

  /* ---------------- per-scene build（幕内相对时间） ---------------- */
  function buildScene(tl, data) {
    var scene = data.scene;
    var lines = data.lines || [];
    var dur = data.duration || 10;

    var root = resolveSceneRoot(scene.id);
    if (!root) {
      if (window.console) console.error('[console-v1] scene root not found:', scene.id);
      return tl;
    }
    var inner = root.querySelector('.scene-inner');
    if (!inner) {
      inner = E('div', 'scene-inner');
      inner.setAttribute('data-layout-allow-overflow', '1');
      inner.setAttribute('data-layout-allow-overlap', '1');
      root.appendChild(inner);
    }

    var byId = {};
    var arrows = [];
    var ei = 0;

    /* ---- 真实素材镜头运动（Screen Studio 式：窗口内缓慢推近/平移） ---- */
    var fw = inner.querySelector('.footage-wrap');
    if (fw) {
      var fi = fw.querySelector('.footage-inner') || fw.querySelector('.footage');
      var cam = (data.footage && data.footage.cam) || {};
      if (fi) {
        var z0 = cam.z ? cam.z[0] : 1.0, z1 = cam.z ? cam.z[1] : 1.07;
        var cx0 = cam.x ? cam.x[0] : 0, cx1 = cam.x ? cam.x[1] : 0;
        var cy0 = cam.y ? cam.y[0] : 0, cy1 = cam.y ? cam.y[1] : 0;
        var cd = Math.max(2.0, dur - 0.7);
        var cst = cam.start == null ? 0.2 : cam.start;
        fi.style.transformOrigin = 'center center';
        tl.fromTo(fi, { scale: z0, x: cx0, y: cy0 },
          { scale: z1, x: cx1, y: cy1, duration: cd, ease: cam.ease || 'power1.inOut' }, cst);
      }
    }

    lines.forEach(function (ln) {
      var t0 = ln.start || 0;
      (ln.elements || []).forEach(function (e) {
        var node;
        switch (e.type) {
          case 'frame': node = buildFrame(e); break;
          case 'grid': node = buildGrid(e); break;
          case 'pill': node = buildPill(e); break;
          case 'hairline': node = buildHairline(e); break;
          case 'bignum': node = buildBignum(e); break;
          case 'slot': node = buildSlot(e); break;
          case 'paper': node = buildPaper(e); break;
          case 'toast': node = buildToast(e); break;
          case 'text': node = buildText(e); break;
          case 'source': node = buildSource(e); break;
          case 'seal': node = buildSeal(e); break;
          case 'panel': node = buildPanel(e); break;
          case 'win': node = buildWin(e); break;
          case 'term': node = buildTerm(e); break;
          case 'rows': node = buildRows(e); break;
          case 'repocard': node = buildRepoCard(e); break;
          case 'mark': node = buildMark(e); break;
          case 'bars': node = buildBars(e); break;
          case 'shape': node = buildShape(e); break;
          case 'image': node = buildImage(e); break;
          case 'leader': node = buildConnector(e); break;
          case 'bracket': node = buildConnector(e); break;
          case 'arrow': node = buildConnector(e); break;
          default: return;
        }
        node.id = e.id || (scene.id + '-e' + (ei++));
        node._spec = e;
        byId[node.id] = node;
        inner.appendChild(node);
        if (e.type === 'arrow' || e.type === 'leader' || e.type === 'bracket') arrows.push(node);
        animElement(tl, node, e, t0 + (e.enter_offset || 0) + 0.02);
      });
    });

    var layoutArrows = function () {
      var r = root.getBoundingClientRect();
      arrows.forEach(function (svg) { svg._needsLayout = false; resolveConnector(svg, byId, r); });
      return true;
    };
    /* 先无条件解析一次：有 spec 几何的端点完全不依赖布局（渲染器安全）；
       仍依赖 DOM 测量的端点标记 _needsLayout，等布局就绪后重测 */
    layoutArrows();
    var needsRetry = false;
    arrows.forEach(function (svg) { if (svg._needsLayout) needsRetry = true; });
    if (needsRetry && window.gsap) {
      var retry = function () {
        var r = root.getBoundingClientRect();
        if (!r.width || !r.height) return;
        arrows.forEach(function (svg) {
          if (svg._needsLayout) { svg._needsLayout = false; resolveConnector(svg, byId, r); }
        });
        gsap.ticker.remove(retry);
        if (tl.eventCallback) tl.eventCallback('onUpdate', null);
      };
      gsap.ticker.add(retry);
      tl.eventCallback('onUpdate', retry);
    }

    /* ---- 幕间转场（enter/exit：fade / zoom / push-left / push-up / rise） ---- */
    var tr = data.transition || {};
    var ent = tr.enter || 'fade';
    if (ent === 'zoom') {
      tl.fromTo(inner, { opacity: 0, scale: 1.055 }, { opacity: 1, scale: 1, duration: 0.62, ease: 'power3.out' }, 0.02);
    } else if (ent === 'push-left') {
      tl.fromTo(inner, { opacity: 0, x: 130 }, { opacity: 1, x: 0, duration: 0.58, ease: 'power3.out' }, 0.02);
    } else if (ent === 'push-up') {
      tl.fromTo(inner, { opacity: 0, y: 96 }, { opacity: 1, y: 0, duration: 0.58, ease: 'power3.out' }, 0.02);
    } else if (ent === 'rise') {
      tl.fromTo(inner, { opacity: 0, y: 48, scale: 1.02 }, { opacity: 1, y: 0, scale: 1, duration: 0.55, ease: 'power3.out' }, 0.02);
    } else {
      tl.set(inner, { opacity: 1 }, 0.02);
    }
    var ext = tr.exit || 'fade';
    var eT = Math.max(0.05, dur - 0.42);
    if (ext === 'zoom-out') {
      tl.to(inner, { opacity: 0, scale: 1.05, duration: 0.4, ease: 'power2.in' }, eT);
    } else if (ext === 'push-left') {
      tl.to(inner, { opacity: 0, x: -130, duration: 0.4, ease: 'power2.in' }, eT);
    } else if (ext === 'push-up') {
      tl.to(inner, { opacity: 0, y: -96, duration: 0.4, ease: 'power2.in' }, eT);
    } else {
      tl.to(inner, { opacity: 0, duration: 0.3, ease: 'power1.in' }, eT);
    }
    return tl;
  }

  /* ---------------- host build（宿主级：字幕条 + BGM） ---------------- */
  function fmtTime(t) {
    t = Math.max(0, t || 0);
    var m = Math.floor(t / 60), s = Math.floor(t % 60);
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
  }

  function buildHost(tl, data) {
    var subs = data.subs || [];
    var total = data.total || 10;
    var bar = document.getElementById('sub-bar');
    var txt = document.getElementById('sub-text');
    var tm = document.getElementById('sub-time');

    if (bar && subs.length) {
      var setSub = function (i) {
        txt.textContent = subs[i].text;
        tm.textContent = fmtTime(subs[i].start);
      };
      tl.set(bar, { opacity: 1 }, subs[0].start);
      for (var k = 0; k < subs.length; k++) {
        (function (i) {
          var sb = subs[i];
          var nx = subs[i + 1];
          tl.call(function () { setSub(i); }, null, sb.start);
          tl.fromTo(txt, { opacity: 0.25 }, { opacity: 1, duration: 0.12, ease: 'power1.out' }, sb.start);
          if (nx) {
            var gap = nx.start - sb.end;
            if (gap >= 0.3) {
              tl.to(bar, { opacity: 0, duration: 0.16, ease: 'power2.in' }, sb.end + 0.05);
              tl.to(bar, { opacity: 1, duration: 0.2, ease: 'power2.out' }, nx.start - 0.18);
            }
          } else {
            tl.to(bar, { opacity: 0, duration: 0.3, ease: 'power2.in' }, sb.end + 0.15);
          }
        })(k);
      }
    }

    /* HUD 章节指示（随片翻页） */
    var chapters = data.chapters || [];
    var chId = document.getElementById('hud-ch-id');
    var chName = document.getElementById('hud-ch-name');
    if (chId && chName && chapters.length) {
      var nCh = chapters.length;
      var pad = function (n) { return (n < 10 ? '0' : '') + n; };
      var setCh = function (i) {
        chId.textContent = 'CH ' + pad(i + 1) + ' / ' + pad(nCh);
        chName.textContent = chapters[i].title;
      };
      setCh(0);
      for (var c = 1; c < chapters.length; c++) {
        (function (i) {
          tl.call(function () { setCh(i); }, null, chapters[i].start + 0.01);
        })(c);
      }
    }

    /* HUD 进度轨（填色 + 游标，全程匀速） */
    var fill = document.getElementById('hud-progress-fill');
    if (fill && total > 0) {
      tl.fromTo(fill, { scaleX: 0 }, { scaleX: 1, duration: total, ease: 'none' }, 0);
    }
    var head = document.getElementById('hud-progress-head');
    if (head && total > 0) {
      tl.fromTo(head, { x: 0 }, { x: 1908, duration: total, ease: 'none' }, 0);
    }

    if (data.bgm) {
      var bgm = document.getElementById('bgm');
      if (bgm) tl.to(bgm, { volume: 0, duration: Math.min(3.5, total * 0.12), ease: 'power1.in' }, Math.max(0, total - 3.5));
    }
    return tl;
  }

  window.ConsoleWorld = { buildScene: buildScene, buildHost: buildHost };
})();
