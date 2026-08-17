/* ============================================================
   Советник у площадки, разговор с ним и усиленное испытание
   ============================================================ */

/* ---------------- фигура в балахоне ---------------- */

/* Модель строится вокруг пояса: так сальто крутится вокруг центра тела,
   а не вокруг пяток. */
function buildSith() {
  const m = meshBuilder();
  const cloth = [0.050, 0.046, 0.058];
  const clothMid = [0.085, 0.078, 0.095];
  const clothLit = [0.130, 0.118, 0.142];
  const sash = [0.10, 0.07, 0.07];
  const skin = [0.70, 0.63, 0.55];
  const skinDark = [0.46, 0.40, 0.36];
  const hilt = [0.26, 0.26, 0.28];
  const hiltLit = [0.66, 0.66, 0.70];
  const hiltDark = [0.14, 0.14, 0.16];

  /* Балахон складками: радиус подола гуляет по углу, и каждая грань
     красится своим тоном — так ткань перестаёт быть гладким конусом. */
  const seg = 26;
  const fold = (a) => 0.50 + 0.055 * Math.sin(a * 5) + 0.03 * Math.sin(a * 9 + 1.1);
  for (let i = 0; i < seg; i++) {
    const a0 = (i / seg) * TAU, a1 = ((i + 1) / seg) * TAU;
    const r0 = fold(a0), r1 = fold(a1);
    const rt = 0.29;
    const shade = 0.5 + 0.5 * Math.sin(a0 * 5);
    const c = shade > 0.66 ? clothLit : shade > 0.33 ? clothMid : cloth;
    // подол, средняя часть и грудь — три яруса, чтобы складка шла по всей высоте
    m.quad([Math.cos(a0) * r0, -0.94, Math.sin(a0) * r0],
           [Math.cos(a1) * r1, -0.94, Math.sin(a1) * r1],
           [Math.cos(a1) * (rt + (r1 - rt) * 0.45), -0.30, Math.sin(a1) * (rt + (r1 - rt) * 0.45)],
           [Math.cos(a0) * (rt + (r0 - rt) * 0.45), -0.30, Math.sin(a0) * (rt + (r0 - rt) * 0.45)], c);
    m.quad([Math.cos(a0) * (rt + (r0 - rt) * 0.45), -0.30, Math.sin(a0) * (rt + (r0 - rt) * 0.45)],
           [Math.cos(a1) * (rt + (r1 - rt) * 0.45), -0.30, Math.sin(a1) * (rt + (r1 - rt) * 0.45)],
           [Math.cos(a1) * rt, 0.42, Math.sin(a1) * rt],
           [Math.cos(a0) * rt, 0.42, Math.sin(a0) * rt], c);
    m.tri([0, -0.97, 0], [Math.cos(a1) * r1, -0.94, Math.sin(a1) * r1],
          [Math.cos(a0) * r0, -0.94, Math.sin(a0) * r0], cloth);
  }
  // пояс: витой шнур в два оборота
  for (let k = 0; k < 2; k++) {
    const nodes = [];
    for (let i = 0; i <= 20; i++) {
      const a = (i / 20) * TAU;
      nodes.push([Math.cos(a) * 0.315, -0.13 - k * 0.06 + Math.sin(a * 3) * 0.012, Math.sin(a) * 0.30]);
    }
    m.rope(nodes, nodes.map(() => 0.022), sash, 5);
  }
  // свисающий конец пояса
  m.rope([[0.10, -0.17, 0.30], [0.13, -0.42, 0.33], [0.11, -0.66, 0.31]],
         [0.020, 0.017, 0.012], sash, 5);

  // плечи и накидка поверх балахона
  m.blob(0, 0.44, 0, 0.37, 0.20, 0.29, clothMid, 12, 7);
  for (let i = 0; i < 16; i++) {
    const a0 = (i / 16) * TAU, a1 = ((i + 1) / 16) * TAU;
    const rr = 0.40 + 0.03 * Math.sin(a0 * 4);
    m.quad([Math.cos(a0) * 0.30, 0.46, Math.sin(a0) * 0.26],
           [Math.cos(a1) * 0.30, 0.46, Math.sin(a1) * 0.26],
           [Math.cos(a1) * rr, 0.02, Math.sin(a1) * rr * 0.9],
           [Math.cos(a0) * rr, 0.02, Math.sin(a0) * rr * 0.9],
           i % 2 ? cloth : clothMid);
  }

  /* Руки: широкий рукав до локтя, узкий манжет, кисть с пальцами. */
  for (const sx of [-1, 1]) {
    m.rope([[sx * 0.30, 0.44, 0.01], [sx * 0.36, 0.16, 0.05], [sx * 0.34, -0.10, 0.11]],
           [0.15, 0.14, 0.115], clothMid, 7);
    m.rope([[sx * 0.34, -0.10, 0.11], [sx * 0.33, -0.24, 0.15]], [0.075, 0.055], cloth, 6);
    // ладонь
    const hx = sx * 0.325, hy = -0.31, hz = 0.18;
    m.blob(hx, hy, hz, 0.048, 0.055, 0.036, skin, 8, 5);
    // четыре пальца и большой
    for (let f = 0; f < 4; f++) {
      const o = (f - 1.5) * 0.023;
      m.rope([[hx + o * 0.6, hy - 0.03, hz + 0.02], [hx + o, hy - 0.085, hz + 0.045]],
             [0.013, 0.010], skin, 4);
    }
    m.rope([[hx - sx * 0.035, hy - 0.01, hz + 0.01], [hx - sx * 0.062, hy - 0.05, hz + 0.035]],
           [0.014, 0.011], skin, 4);
  }

  /* Капюшон: внешний конус складками, тёмная подкладка и лицо в тени. */
  for (let i = 0; i < 18; i++) {
    const a0 = (i / 18) * TAU, a1 = ((i + 1) / 18) * TAU;
    const r = 0.285 + 0.018 * Math.sin(a0 * 6);
    const c = i % 3 ? cloth : clothMid;
    m.quad([Math.cos(a0) * r, 0.50, Math.sin(a0) * r - 0.02],
           [Math.cos(a1) * r, 0.50, Math.sin(a1) * r - 0.02],
           [Math.cos(a1) * 0.12, 1.00, Math.sin(a1) * 0.12 - 0.07],
           [Math.cos(a0) * 0.12, 1.00, Math.sin(a0) * 0.12 - 0.07], c);
  }
  // подкладка капюшона: почти чёрная, за счёт неё лицо в тени
  m.blob(0, 0.71, -0.03, 0.225, 0.255, 0.235, [0.020, 0.018, 0.024], 12, 7);
  // козырёк капюшона нависает над лбом
  for (let i = 0; i < 12; i++) {
    const a0 = -1.2 + (i / 12) * 2.4, a1 = -1.2 + ((i + 1) / 12) * 2.4;
    m.quad([Math.sin(a0) * 0.24, 0.86, 0.16 + Math.cos(a0) * 0.06],
           [Math.sin(a1) * 0.24, 0.86, 0.16 + Math.cos(a1) * 0.06],
           [Math.sin(a1) * 0.20, 0.74, 0.235 + Math.cos(a1) * 0.05],
           [Math.sin(a0) * 0.20, 0.74, 0.235 + Math.cos(a0) * 0.05], cloth);
  }

  /* Лицо: череп, надбровья, нос, впалые щёки, губы и блики глаз.
     Всё в тени капюшона, поэтому берём приглушённые тона. */
  m.blob(0, 0.685, 0.09, 0.105, 0.125, 0.095, skinDark, 12, 8);
  m.blob(0, 0.735, 0.135, 0.088, 0.045, 0.055, skinDark, 9, 5);      // лоб
  for (const sx of [-1, 1]) {
    m.blob(sx * 0.043, 0.716, 0.160, 0.036, 0.018, 0.022, skin, 7, 4);   // надбровье
    m.blob(sx * 0.040, 0.690, 0.163, 0.020, 0.014, 0.010, [0.86, 0.80, 0.62], 6, 4);
    m.blob(sx * 0.040, 0.690, 0.170, 0.009, 0.009, 0.005, [0.55, 0.12, 0.08], 5, 4);
    m.blob(sx * 0.085, 0.672, 0.115, 0.030, 0.040, 0.030, skinDark, 7, 5);  // впалая щека
  }
  m.blob(0, 0.672, 0.175, 0.020, 0.036, 0.028, skin, 7, 5);           // нос
  m.blob(0, 0.640, 0.168, 0.030, 0.010, 0.014, [0.42, 0.30, 0.28], 7, 4);  // губы
  m.blob(0, 0.612, 0.150, 0.048, 0.032, 0.035, skinDark, 8, 5);       // подбородок

  /* Рукоять: набалдашник, рифлёная хватка, кольца и эмиттер. */
  const hx = 0.325, hy = -0.31, hz = 0.18;
  m.rope([[hx, hy - 0.10, hz + 0.05], [hx, hy - 0.06, hz + 0.04]], [0.030, 0.034], hiltDark, 8);
  for (let i = 0; i < 6; i++) {
    const y0 = hy - 0.06 + i * 0.026;
    m.rope([[hx, y0, hz + 0.04 - i * 0.002], [hx, y0 + 0.018, hz + 0.04 - i * 0.002]],
           [i % 2 ? 0.033 : 0.029, i % 2 ? 0.033 : 0.029], i % 2 ? hilt : hiltDark, 8);
  }
  m.rope([[hx, hy + 0.10, hz + 0.028], [hx, hy + 0.13, hz + 0.026]], [0.036, 0.032], hiltLit, 8);
  m.rope([[hx, hy + 0.13, hz + 0.026], [hx, hy + 0.16, hz + 0.024]], [0.028, 0.024], hiltDark, 8);
  m.box(hx + 0.034, hy + 0.02, hz + 0.042, 0.008, 0.030, 0.012, 0, [0.62, 0.16, 0.12]);  // клавиша
  return m.pack();
}

/** Клинок: светящееся ядро и ореол вокруг. Рисуем аддитивно. */
function buildBlade() {
  const pos = [], fade = [], idx = [];
  const tube = (r, f, y0, y1) => {
    const seg = 8, base = pos.length / 3;
    for (let i = 0; i <= seg; i++) {
      const a = (i / seg) * TAU;
      pos.push(0.325 + Math.cos(a) * r, y0, 0.204 + Math.sin(a) * r);
      pos.push(0.325 + Math.cos(a) * r, y1, 0.204 + Math.sin(a) * r);
      fade.push(f, f);
    }
    for (let i = 0; i < seg; i++) {
      const a = base + i * 2;
      idx.push(a, a + 1, a + 3, a, a + 3, a + 2);
    }
    // торец
    const cap = pos.length / 3;
    pos.push(0.325, y1, 0.204); fade.push(f);
    for (let i = 0; i < seg; i++) idx.push(cap, base + i * 2 + 1, base + (i + 1) * 2 + 1);
  };
  tube(0.021, 1.0, -0.15, 1.18);      // ядро
  tube(0.052, 0.30, -0.15, 1.20);     // ореол
  return { pos: buffer(new Float32Array(pos)), fade: buffer(new Float32Array(fade)),
           idx: buffer(new Uint16Array(idx), gl.ELEMENT_ARRAY_BUFFER), count: idx.length };
}

const SITH = {
  x: G.sith.x, z: G.sith.z, yaw: 0,
  y: 0,               // высота пояса над землёй
  flip: 0,            // фаза сальто, 0..1
  flipAt: 12,         // когда сделает следующее
  greeted: false,
  model: m4(),
  saber: 0.3,         // выдвинутость клинка
  talk: 0,            // сколько ещё говорит
  follow: false,      // идёт следом и садится в машину
  step: 0,            // фаза шага, для покачивания на ходу
  guard: 0,           // сколько ещё отбивается от нападающих
  target: null,       // кого сейчас отгоняет
};

/**
 * Стоит, покачивается, крутит клинок и время от времени делает сальто
 * назад. Во время разговора поворачивается к собеседнику.
 */
function updateSith(dt) {
  if (game.world !== 'gamma') { SITH.flip = 0; return; }
  const s = SITH;

  /* В машине советник занимает пассажирское место: садится и выходит
     вместе с водителем, отдельной команды не нужно. */
  if (s.follow && CAR.inside) {
    const co = Math.cos(CAR.yaw), si = Math.sin(CAR.yaw);
    s.x = CAR.x + co * 0.52 - si * 0.10;
    s.z = CAR.z + si * 0.52 + co * 0.10;
    s.y = CAR.y + 1.20;
    s.yaw = CAR.yaw;
    s.flip = 0;
    s.saber = damp(s.saber, 0.12, 2.2, dt);
    s.talk = Math.max(0, s.talk - dt);
    m4compose(s.model, s.x, s.y, s.z, s.yaw, 0, 0, 0.86);
    return;
  }

  const dx = cam.x - s.x, dz = cam.z - s.z;
  const dist = Math.hypot(dx, dz);
  let moving = 0;

  if (s.follow) {
    // держимся в паре шагов позади-справа, отстали — прибавляем шаг
    const want = 2.8;
    if (dist > 45) {
      // отстал слишком сильно — появляется за спиной, чтобы не бежать полкилометра
      const back = cam.yaw + Math.PI;
      s.x = cam.x + Math.sin(back) * 3.2;
      s.z = cam.z - Math.cos(back) * 3.2;
    } else if (dist > want) {
      const sp = Math.min(4.2 + (dist - want) * 2.2, 22);
      const k = Math.min(sp * dt / dist, 1);
      s.x += dx * k; s.z += dz * k;
      moving = Math.min(sp / 4, 1);
    }
    s.yaw = damp(s.yaw, Math.atan2(dx, -dz), 5, dt);
  } else if (dist < 30) {
    s.yaw = damp(s.yaw, Math.atan2(dx, -dz), 3, dt);
  }

  // если он кого-то отгоняет, смотрит на нападающего и держит клинок
  if (s.guard > 0) {
    s.guard -= dt;
    if (s.target) {
      s.yaw = damp(s.yaw, Math.atan2(s.target.x - s.x, -(s.target.z - s.z)), 7, dt);
    }
    if (s.guard <= 0) s.target = null;
  }

  const near = dist < 30 || s.follow;
  s.saber = damp(s.saber, near || s.flip > 0 || s.guard > 0 ? 1 : 0.15, 2.2, dt);
  s.talk = Math.max(0, s.talk - dt);

  s.flipAt -= dt;
  if (s.flip === 0 && s.flipAt <= 0 && near && s.guard <= 0) {
    s.flip = 0.0001; s.flipAt = 14 + Math.random() * 16;
  }
  if (s.flip > 0) {
    s.flip += dt / 1.15;                      // сальто длится чуть больше секунды
    if (s.flip >= 1) s.flip = 0;
  }
  const f = s.flip;
  const jump = f > 0 ? Math.sin(f * Math.PI) * 2.4 : 0;
  const spin = f > 0 ? -f * TAU : 0;
  s.step += dt * (6 + moving * 8) * (moving > 0.02 ? 1 : 0.12);
  const bob = Math.sin(s.step) * (0.02 + moving * 0.06)
            + (s.talk > 0 ? Math.sin(game.proper * 9) * 0.02 : 0);
  const lean = moving * 0.10 + (s.guard > 0 ? 0.08 : 0);
  s.y = gammaMeshH(s.x, s.z) + 0.98 + jump + bob;
  m4compose(s.model, s.x, s.y, s.z, s.yaw, spin + lean, Math.sin(s.step * 0.5) * moving * 0.04, 1);
}

/** Включить или выключить сопровождение. */
function sithFollow(on) {
  if (SITH.follow === on) return;
  SITH.follow = on;
  if (on) {
    SITH.x = cam.x - 2.4; SITH.z = cam.z - 2.4;
    sithSay('Иду за вами. Постарайтесь не оборачиваться слишком часто.');
  } else {
    sithSay('Останусь здесь. Позовёте — приду.');
  }
}

/* ---------------- разговор ---------------- */

const SITH_LINES = [
  { k: ['привет', 'здоров', 'хай', 'ку', 'hello', 'дароу'],
    a: ['Приветствую. Полигон в вашем распоряжении.',
        'Наконец-то. Я ждал вас дольше, чем следовало.'] },
  { k: ['кто ты', 'кто вы', 'имя', 'как тебя', 'представ'],
    a: ['Я ваш советник. Имя моё вам ничего не даст, а вот совет — многое.',
        'Тот, кто стоит за плечом и подсказывает. Этого достаточно.'] },
  { k: ['бомб', 'взрыв', 'испытан', 'ядер', 'заряд'],
    a: ['Кнопка справа. Заряд уйдёт на мишенное поле — оно в полутора километрах.',
        'Смотрите не на вспышку, а на то, что от построек останется.',
        'Из города зрелище безопаснее. И, признаться, красивее.'] },
  { k: ['сальто', 'прыг', 'кувырок', 'акробат'],
    a: ['Извольте.', 'Смотрите внимательно, повторять не буду.'] },
  { k: ['меч', 'клинок', 'сабл', 'светов'],
    a: ['Красный. Другие цвета я нахожу сентиментальными.',
        'Клинок — это довод. Обычно последний.'] },
  { k: ['город', 'уехать', 'машин', 'ехать', 'авто'],
    a: ['Машина у площадки. Пять километров по прямой — и вы в городе.',
        'В машине жмите газ и не сворачивайте с дороги. Или включите автопилот.'] },
  { k: ['бассейн', 'золот', 'вода', 'купать'],
    a: ['Золото — не роскошь, а напоминание, кому здесь принадлежит вода.',
        'Бассейн западнее площадки. Полотенца не предусмотрены.'] },
  { k: ['море', 'океан', 'берег', 'пляж'],
    a: ['Море к западу. Дальше него нет ничего интересного.'] },
  { k: ['дерев', 'лес', 'роща', 'трава'],
    a: ['Роща здесь недолговечна. Вы сами скоро поймёте почему.'] },
  { k: ['земля', 'домой', 'вернут', 'ракет', 'улет'],
    a: ['Ракета ждёт. Выберите цель «Земля» и не оглядывайтесь.'] },
  { k: ['квазар', 'дыр', 'чёрн', 'черн'],
    a: ['Квазар — это чужая гравитация. К ней стоит подходить с уважением.'] },
  { k: ['сила', 'ситх', 'джедай', 'орден', 'тьм', 'темн'],
    a: ['Сила — это не мистика. Это умение довести дело до конца.',
        'Джедаи проповедуют равновесие. Равновесие — это когда обе чаши пусты.'] },
  { k: ['зачем', 'смысл', 'почему'],
    a: ['Затем, что вы можете. Остальные оправдания придумают потом.'] },
  { k: ['помощ', 'что делать', 'как', 'подскаж'],
    a: ['Бомба — кнопка справа или клавиша B. Машина — подойти и нажать E.',
        'Хотите зрелище — уезжайте в город и запускайте оттуда.'] },
  { k: ['спасиб', 'благодар'],
    a: ['Не благодарите. Я записываю.'] },
  { k: ['пока', 'прощай', 'до свид'],
    a: ['Идите. Я останусь — мне здесь спокойно.'] },
  { k: ['пойдём', 'пойдем', 'со мной', 'идём со', 'идем со', 'сопровожд', 'за мной'],
    a: ['__FOLLOW_ON__'] },
  { k: ['останься', 'жди здесь', 'подожди', 'стой тут', 'не иди'],
    a: ['__FOLLOW_OFF__'] },
  { k: ['кафе', 'кофе', 'бариста', 'выпить', 'перекус'],
    a: ['В городе есть заведение с открытым фасадом. Бариста там внимательнее меня.',
        'Кофе не проясняет мысли. Но руки перестают дрожать после испытаний.'] },
  { k: ['напад', 'хулиган', 'прохож', 'защит', 'бандит', 'драк'],
    a: ['В городе бывают невежливые. Держитесь рядом — я разберусь.',
        'Пока я иду за вами, к вам никто не подойдёт дважды.'] },
];

const SITH_DEFAULT = [
  'Занятная мысль. Но у нас испытания.',
  'Возможно. А возможно, вы просто тянете время.',
  'Я слышал. И сделал вид, что не услышал.',
  'Сформулируйте иначе — и, быть может, я отвечу.',
  'Полигон не любит долгих разговоров.',
];

let sithReplyIdx = 0;

function sithReply(text) {
  const t = text.toLowerCase();
  for (const g of SITH_LINES) {
    if (g.k.some((k) => t.includes(k))) {
      if (g.k.includes('сальто') && SITH.flip === 0) SITH.flip = 0.0001;
      const a = g.a[(sithReplyIdx++) % g.a.length];
      // две реплики не отвечают, а переключают поведение
      if (a === '__FOLLOW_ON__') { setTimeout(() => sithFollow(true), 0); return 'Как скажете.'; }
      if (a === '__FOLLOW_OFF__') { setTimeout(() => sithFollow(false), 0); return 'Как скажете.'; }
      return a;
    }
  }
  return SITH_DEFAULT[(sithReplyIdx++) % SITH_DEFAULT.length];
}

function sithSay(text) {
  const box = document.getElementById('sith-say');
  if (!box) return;
  box.textContent = text;
  box.classList.add('show');
  SITH.talk = Math.min(6, 1.6 + text.length * 0.045);
  clearTimeout(sithSay.timer);
  sithSay.timer = setTimeout(() => box.classList.remove('show'), SITH.talk * 1000);
}

function sithGreet() {
  if (SITH.greeted) return;
  SITH.greeted = true;
  SITH.flip = 0.0001;
  sithSay('Добро пожаловать на Гамму. Я ваш советник. Спрашивайте — или начинайте испытания.');
}

/** Достаточно ли близко, чтобы завести разговор. */
function talkReady() {
  return game.world === 'gamma' && !CAR.inside && !game.rocket.inside
    && !game.tent.inside && Math.hypot(cam.x - SITH.x, cam.z - SITH.z) < 26;
}

/** Открыть разговор нажатием — на планшете это единственный путь. */
function talkClose() {
  if (game.world !== 'gamma' || CAR.inside || game.rocket.inside) return false;
  if (Math.hypot(cam.x - SITH.x, cam.z - SITH.z) > 5.5) return false;
  if (document.getElementById('talk').classList.contains('show')) return false;
  openTalk();
  return true;
}

let talkBtnShown = false;

/** Кнопка «Поговорить» висит, пока советник рядом. */
function syncTalkUI() {
  const btn = document.getElementById('talk-btn');
  if (!btn) return;
  const show = talkReady() && !document.getElementById('talk').classList.contains('show');
  if (show !== talkBtnShown) { talkBtnShown = show; btn.classList.toggle('show', show); }
}

function openTalk() {
  if (game.world !== 'gamma') return;
  if (Math.hypot(cam.x - SITH.x, cam.z - SITH.z) > 26) { toast('Советник слишком далеко'); return; }
  const w = document.getElementById('talk');
  w.classList.add('show');
  document.getElementById('app').classList.add('talking');
  refreshChips();
  // на планшете фокус в поле поднимает клавиатуру поверх реплик — не лезем
  if (!window.matchMedia('(pointer: coarse)').matches) document.getElementById('talk-input').focus();
}

function closeTalk() {
  if (voice.on && voice.rec) { try { voice.rec.stop(); } catch (e) {} }
  document.getElementById('talk').classList.remove('show');
  document.getElementById('app').classList.remove('talking');
  document.getElementById('talk-input').blur();
}

/* ---------------- усиленное испытание ---------------- */

/* Ударная волна теперь валит с ног, оглушает и рушит постройки. */
const HIT = {
  vx: 0, vz: 0,        // отброс наблюдателя
  down: 0,             // насколько присели/упали, метры
  deaf: 0,             // глухота и звон, 0..1
};

const deafSnd = { osc: null, gain: null, osc2: null };

/** Звон в ушах: две близкие частоты, медленно затухают. */
function startTinnitus(power) {
  if (!audio.ctx || !audio.on) return;
  const ctx = audio.ctx, out = audio.master || ctx.destination;
  stopTinnitus();
  const g = ctx.createGain();
  g.gain.setValueAtTime(0.0001, ctx.currentTime);
  g.gain.exponentialRampToValueAtTime(0.055 * power, ctx.currentTime + 0.12);
  g.connect(out);
  const o1 = ctx.createOscillator();
  o1.type = 'sine'; o1.frequency.value = 3950;
  const o2 = ctx.createOscillator();
  o2.type = 'sine'; o2.frequency.value = 4090;
  o1.connect(g); o2.connect(g);
  o1.start(); o2.start();
  deafSnd.osc = o1; deafSnd.osc2 = o2; deafSnd.gain = g;
}

function stopTinnitus() {
  if (!deafSnd.osc) return;
  try { deafSnd.osc.stop(); deafSnd.osc2.stop(); } catch (e) {}
  deafSnd.osc = null; deafSnd.osc2 = null; deafSnd.gain = null;
}

/**
 * Приход фронта: сбивает с ног, оглушает, рвёт постройки и поджигает лес.
 * Сила падает как обратный квадрат расстояния.
 */
function shockArrival() {
  const bx = BLAST.pos[0], bz = BLAST.pos[2];
  const px = CAR.inside ? CAR.x : cam.x, pz = CAR.inside ? CAR.z : cam.z;
  const d = Math.max(Math.hypot(px - bx, pz - bz), 40);
  const power = clamp(700 / d, 0, 1.6);

  // отброс: скорость от эпицентра плюс падение на землю
  const nx = (px - bx) / d, nz = (pz - bz) / d;
  HIT.vx += nx * power * 16;
  HIT.vz += nz * power * 16;
  if (power > 0.25 && !CAR.inside) HIT.down = Math.min(1.25, HIT.down + power * 1.1);
  if (CAR.inside) { CAR.speed += power * 8; CAR.yaw += (Math.random() - 0.5) * power * 0.5; }

  // оглушение
  HIT.deaf = Math.min(1, HIT.deaf + power * 0.9);
  if (HIT.deaf > 0.12) {
    startTinnitus(clamp(HIT.deaf, 0.2, 1));
    toast('Звон в ушах');
  }

  // постройки
  for (const b of BUILDINGS) {
    const bd = Math.hypot(b.x - bx, b.z - bz);
    const p = clamp(820 / Math.max(bd, 60) / b.tough - 0.35, 0, 1.4);
    if (p > 0.05) shockBuilding(b, p);
  }

  // лес: ближние ломает, дальние поджигает
  const dirty = new Set();
  for (let i = 0; i < TREES.length; i++) {
    const t = TREES[i];
    const td = Math.hypot(t.x - bx, t.z - bz);
    if (td > 900) continue;
    const p = clamp(620 / Math.max(td, 60) - 0.35, 0, 1.4);
    if (p <= 0.02) continue;
    let changed = false;
    if (p > 0.55 && t.fell < 1) { t.fell = 1; t.fellDir = Math.atan2(t.z - bz, t.x - bx); changed = true; }
    if (p > 0.12 && t.burn < 1) {
      t.burn = 1; changed = true;
      FIRES.push({ x: t.x, z: t.z, y: t.y, r: 2.2 + t.s * 2.4,
                   life: 70 + Math.random() * 60, age: 0, seed: Math.random() * 100, next: Math.random() * 0.3 });
    }
    if (changed) dirty.add((i / TREE_CHUNK) | 0);
  }
  for (const c of dirty) rebuildTreeChunk(c);
  if (FIRES.length > 220) FIRES.splice(0, FIRES.length - 220);
}

/** Отброс и подъём на ноги, затухание глухоты. */
function updateHit(dt) {
  if (Math.abs(HIT.vx) + Math.abs(HIT.vz) > 0.01) {
    const k = Math.exp(-3.2 * dt);
    if (!CAR.inside) {
      cam.x += HIT.vx * dt;
      cam.z += HIT.vz * dt;
    }
    HIT.vx *= k; HIT.vz *= k;
  }
  // встаём примерно за две секунды
  HIT.down = Math.max(0, HIT.down - dt * 0.62);
  if (HIT.deaf > 0) {
    HIT.deaf = Math.max(0, HIT.deaf - dt / 13);
    if (deafSnd.gain) {
      deafSnd.gain.gain.setTargetAtTime(Math.max(0.0001, 0.055 * HIT.deaf), audio.ctx.currentTime, 1.2);
    }
    // остальной мир на это время глохнет
    if (audio.master) {
      audio.master.gain.setTargetAtTime(Math.max(0.06, 1 - HIT.deaf * 0.85) * (audio.on ? 1 : 0.0001),
        audio.ctx.currentTime, 0.5);
    }
    if (HIT.deaf === 0) stopTinnitus();
  }
}

/* ---------------- звук мотора ---------------- */

/* Гул двигателя: пила через фильтр, частота растёт со скоростью,
   плюс шум шин. Заводится, когда садишься за руль. */
const carSnd = { osc: null, sub: null, filt: null, gain: null, tyre: null, tyreGain: null };

function carSoundStart() {
  if (!audio.ctx || !audio.on || carSnd.osc) return;
  const ctx = audio.ctx, out = audio.master || ctx.destination;

  const gain = ctx.createGain();
  gain.gain.value = 0.0001;
  gain.connect(out);

  const filt = ctx.createBiquadFilter();
  filt.type = 'lowpass';
  filt.frequency.value = 480;
  filt.Q.value = 3.2;
  filt.connect(gain);

  const osc = ctx.createOscillator();
  osc.type = 'sawtooth';
  osc.frequency.value = 42;
  osc.connect(filt);
  osc.start();

  const sub = ctx.createOscillator();
  sub.type = 'square';
  sub.frequency.value = 21;
  const subGain = ctx.createGain();
  subGain.gain.value = 0.35;
  sub.connect(subGain).connect(filt);
  sub.start();

  // шины: шум, который слышно только на ходу
  const len = ctx.sampleRate * 2;
  const buf = ctx.createBuffer(1, len, ctx.sampleRate);
  const d = buf.getChannelData(0);
  let lp = 0;
  for (let i = 0; i < len; i++) { lp = lp * 0.72 + (Math.random() * 2 - 1) * 0.28; d[i] = lp * 2.4; }
  const tyre = ctx.createBufferSource();
  tyre.buffer = buf; tyre.loop = true;
  const tf = ctx.createBiquadFilter();
  tf.type = 'bandpass'; tf.frequency.value = 900; tf.Q.value = 0.7;
  const tg = ctx.createGain();
  tg.gain.value = 0.0001;
  tyre.connect(tf).connect(tg).connect(out);
  tyre.start();

  Object.assign(carSnd, { osc, sub, filt, gain, tyre, tyreGain: tg });
}

function carSoundStop() {
  if (!carSnd.osc) return;
  const t = audio.ctx.currentTime;
  carSnd.gain.gain.setTargetAtTime(0.0001, t, 0.15);
  carSnd.tyreGain.gain.setTargetAtTime(0.0001, t, 0.15);
  const { osc, sub, tyre } = carSnd;
  setTimeout(() => { try { osc.stop(); sub.stop(); tyre.stop(); } catch (e) {} }, 700);
  carSnd.osc = null; carSnd.sub = null; carSnd.gain = null; carSnd.tyre = null; carSnd.tyreGain = null;
}

/** Обороты идут за скоростью, но с «переключением передач». */
function carSoundLevel() {
  if (!carSnd.osc || !audio.ctx) return;
  const t = audio.ctx.currentTime;
  const v = Math.abs(CAR.speed);
  const gear = Math.min(4, Math.floor(v / 15));          // четыре ступени
  const rpm = 0.25 + ((v - gear * 15) / 15) * 0.75;       // обороты внутри передачи
  carSnd.osc.frequency.setTargetAtTime(38 + rpm * 68, t, 0.08);
  carSnd.sub.frequency.setTargetAtTime(19 + rpm * 34, t, 0.08);
  carSnd.filt.frequency.setTargetAtTime(320 + rpm * 780, t, 0.12);
  carSnd.gain.gain.setTargetAtTime(0.035 + rpm * 0.055, t, 0.12);
  carSnd.tyreGain.gain.setTargetAtTime(Math.min(v / 64, 1) * 0.10, t, 0.2);
}

/* ---------------- готовые реплики и голос ---------------- */

/* На планшете печатать неудобно: рядом с полем ввода лежит набор готовых
   фраз, который обновляется после каждого ответа, и кнопка микрофона. */
const TALK_CHIPS = [
  'Привет', 'Кто ты такой?', 'Как запустить бомбу?', 'Покажи сальто',
  'Расскажи про меч', 'Где здесь город?', 'Что за золотой бассейн?',
  'Далеко ли море?', 'Зачем всё это?', 'Что мне тут делать?',
  'Пойдём со мной', 'Останься здесь', 'Расскажи про квазар',
  'Что такое Сила?', 'Где кофе можно выпить?', 'Спасибо',
];

let chipFrom = 0;

/** Показывает четыре свежие реплики, каждый раз сдвигая окно по списку. */
function refreshChips() {
  const box = document.getElementById('talk-chips');
  if (!box) return;
  box.textContent = '';
  for (let i = 0; i < 4; i++) {
    const text = TALK_CHIPS[(chipFrom + i) % TALK_CHIPS.length];
    const b = document.createElement('button');
    b.textContent = text;
    b.addEventListener('click', () => { saySith(text); });
    box.appendChild(b);
  }
  chipFrom = (chipFrom + 4) % TALK_CHIPS.length;
}

/** Общий вход: и печать, и нажатие на реплику, и распознанная речь. */
function saySith(text) {
  const t = (text || '').trim();
  if (!t) return;
  sithSay(sithReply(t));
  refreshChips();
}

/* Распознавание речи браузером. Где его нет — просто прячем кнопку. */
const voice = { rec: null, on: false };

function initVoice() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  const btn = document.getElementById('talk-mic');
  if (!btn) return;
  if (!SR) { btn.classList.add('hidden'); return; }
  const rec = new SR();
  rec.lang = 'ru-RU';
  rec.interimResults = false;
  rec.maxAlternatives = 1;
  rec.continuous = false;
  rec.onresult = (e) => {
    const said = e.results[0] && e.results[0][0] ? e.results[0][0].transcript : '';
    if (said) {
      const inp = document.getElementById('talk-input');
      if (inp) inp.value = '';
      saySith(said);
    }
  };
  rec.onend = () => { voice.on = false; btn.classList.remove('listening'); };
  rec.onerror = (e) => {
    voice.on = false;
    btn.classList.remove('listening');
    if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
      toast('Микрофон не разрешён — выберите реплику или напишите');
    }
  };
  voice.rec = rec;
}

function toggleVoice() {
  const btn = document.getElementById('talk-mic');
  if (!voice.rec || !btn) return;
  if (voice.on) { try { voice.rec.stop(); } catch (e) {} return; }
  try {
    voice.rec.start();
    voice.on = true;
    btn.classList.add('listening');
    toast('Слушаю…');
  } catch (e) { /* уже слушает */ }
}
