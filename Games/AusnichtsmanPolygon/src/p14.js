/* ============================================================
   Лаборатория квантовой механики и КТП
   ------------------------------------------------------------
   Стоит в Неваде между палаткой и тремя поверхностями. Все числа
   на стендах считаются по настоящим формулам от настоящих констант,
   а не подставляются на глаз. Наблюдаемый объект тоже настоящий:
   чёрная дыра этой сцены с её радиусом горизонта.
   ============================================================ */

/* ---------------- физические постоянные, СИ ---------------- */

const PH = {
  hbar: 1.054571817e-34,      // Дж·с
  h: 6.62607015e-34,
  c: 2.99792458e8,            // м/с
  G: 6.67430e-11,             // м³/(кг·с²)
  kB: 1.380649e-23,           // Дж/К
  e: 1.602176634e-19,         // Кл
  me: 9.1093837015e-31,       // кг
  eps0: 8.8541878128e-12,
  Tcmb: 2.7255,               // К, реликтовый фон
  year: 3.155693e7,           // с
};

/* ---------------- формулы Хокинга ---------------- */

/** Масса по радиусу горизонта: rₛ = 2GM/c². */
const bhMass = (rs) => (rs * PH.c * PH.c) / (2 * PH.G);
/** Радиус горизонта по массе. */
const bhRadius = (M) => (2 * PH.G * M) / (PH.c * PH.c);
/** Температура Хокинга: T = ħc³/(8πGMk_B). */
const bhTemp = (M) => (PH.hbar * PH.c ** 3) / (8 * Math.PI * PH.G * M * PH.kB);
/** Светимость по Стефану–Больцману для горизонта: P = ħc⁶/(15360πG²M²). */
const bhPower = (M) => (PH.hbar * PH.c ** 6) / (15360 * Math.PI * PH.G ** 2 * M * M);
/** Полное время испарения: t = 5120πG²M³/(ħc⁴). */
const bhLife = (M) => (5120 * Math.PI * PH.G ** 2 * M ** 3) / (PH.hbar * PH.c ** 4);
/** Энтропия Бекенштейна–Хокинга в единицах k_B: S/k_B = 4πGM²/(ħc). */
const bhEntropy = (M) => (4 * Math.PI * PH.G * M * M) / (PH.hbar * PH.c);
/** Температура Унру для ускорения a: T = ħa/(2πck_B). */
const unruhTemp = (a) => (PH.hbar * a) / (2 * Math.PI * PH.c * PH.kB);

/* Масса дыры этой сцены — от неё пляшут все стенды. */
const BH_M0 = bhMass(BH.rs);

/* ---------------- живая связь со стендом ---------------- */

/* Дыра в Неваде — не декорация: тень, отклонение лучей, ход часов и
   рождение пар считаются от BH.rs каждый кадр. Значит, стенд может
   этим радиусом управлять, и тогда цифры на табло и вид за стеной —
   одно и то же. Больше двенадцати метров горизонт разрастаться не даём:
   он накрыл бы саму площадку. */
BH.rs0 = BH.rs;
BH.rg0 = BH.rg;
BH.block0 = BH.block;
const BH_RS_MAX = 12;
const BH_M_MAX = bhMass(BH_RS_MAX);

/** Подогнать дыру сцены под массу. Возвращает false, если такая не влезает. */
function bhSetMass(M) {
  const rs = bhRadius(M);
  if (!(rs >= 0) || rs > BH_RS_MAX) return false;
  BH.rs = rs;
  BH.rg = BH.rg0 * (rs / BH.rs0);
  BH.block = BH.rg / (1 - 1 / (BH.maxDil * BH.maxDil));
  return true;
}

/** Вернуть дыре её собственный радиус. */
function bhRestore() {
  BH.rs = BH.rs0; BH.rg = BH.rg0; BH.block = BH.block0;
}

/** Угловой размер тени с того места, где мы стоим. */
function bhAngle() {
  const d = Math.hypot(cam.x - BH.pos[0], cam.y - BH.pos[1], cam.z - BH.pos[2]);
  return 2 * Math.atan(BH.rs / Math.max(d, BH.rs * 1.05));
}

/* ---------------- размещение ---------------- */

/* Зал стоит за спиной у входа на поляну: обернулись — и он перед вами,
   палатка справа, поверхности за спиной. Место выбрано по рельефу:
   на всём пятне земля гуляет на треть метра, юбка плиты это закрывает. */
const LAB = { x: -4, z: 34, yaw: 0, w: 11, d: 8 };
LAB.y = terrainH(LAB.x, LAB.z);
LAB.floor = LAB.y + 0.24;

/** Локальные координаты зала в мировые. */
LAB.at = (x, z) => [
  LAB.x + x * Math.cos(LAB.yaw) - z * Math.sin(LAB.yaw),
  LAB.z + x * Math.sin(LAB.yaw) + z * Math.cos(LAB.yaw),
];

/** Внутри ли точка контура здания — по ней выравниваем пол под ногами. */
function inLab(x, z) {
  const dx = x - LAB.x, dz = z - LAB.z;
  const co = Math.cos(-LAB.yaw), si = Math.sin(-LAB.yaw);
  const lx = dx * co - dz * si, lz = dx * si + dz * co;
  return Math.abs(lx) < LAB.w + 0.4 && Math.abs(lz) < LAB.d + 0.4;
}

/* ---------------- стенды ---------------- */

/* Стенды стоят двумя рядами вдоль стен, лицом в проход. Установка строится
   в своих координатах: читающий стоит со стороны −z и смотрит на табло. */
const HALF = Math.PI / 2;
const STATIONS = [
  { id: 'evap',      name: 'Испарение дыры',    lx: -9.2, lz:  5.4, ry:  HALF },
  { id: 'page',      name: 'Кривая Пейджа',     lx: -9.2, lz:  1.8, ry:  HALF },
  { id: 'fiber',     name: 'Горизонт в волокне', lx: -9.2, lz: -1.8, ry:  HALF },
  { id: 'slit',      name: 'Две щели',          lx: -9.2, lz: -5.4, ry:  HALF },
  { id: 'bell',      name: 'Неравенство Белла', lx:  9.2, lz:  5.4, ry: -HALF },
  { id: 'casimir',   name: 'Эффект Казимира',   lx:  9.2, lz:  1.8, ry: -HALF },
  { id: 'schwinger', name: 'Пары по Швингеру',  lx:  9.2, lz: -1.8, ry: -HALF },
  { id: 'tunnel',    name: 'Туннелирование',    lx:  9.2, lz: -5.4, ry: -HALF },
];

for (const s of STATIONS) {
  const [wx, wz] = LAB.at(s.lx, s.lz);
  s.x = wx; s.z = wz;
  s.yaw = LAB.yaw + s.ry;
  // место читающего: на полтора метра со стороны −z установки
  s.sx = s.x + Math.sin(s.yaw) * 2.4;
  s.sz = s.z - Math.cos(s.yaw) * 2.4;
}

/* Состояние опытов. Всё, что накапливается или крутится во времени. */
const LABS = {
  open: null,             // какой стенд открыт
  // испарение: масса задаётся, время идёт в долях полной жизни
  evapM0: BH_M0,
  evapU: 0,               // прожитая доля жизни, 0..1
  evapRun: false,
  evapSpan: 26,           // за столько секунд стенд прокручивает всю жизнь
  evapLive: false,        // связь с дырой за стеной
  evapNote: '',           // почему связь оборвалась
  evapGone: false,        // дыру испарили до конца
  // кривая Пейджа
  pageU: 1 - Math.pow(2, -1.5),
  // волокно: горизонт на фронте импульса
  fibDn: 1.0e-3,          // ступенька показателя на фронте импульса
  fibIn: 1550,            // длина волны пробы, нм
  fibEdge: 2.0e-6,        // длина фронта, м
  fibN: 0,                // сколько фотонов уже переброшено через горизонт
  fibOn: false,
  // двухщелевой
  slitDots: [],           // [x, y] в долях экрана
  slitWhich: false,       // включён детектор пути
  slitRate: 150,          // электронов в секунду
  slitAcc: 0,
  slitGap: 300e-9,        // расстояние между щелями, м
  slitE: 60,              // энергия электрона, эВ
  // Белл
  bellA: 0, bellA2: Math.PI / 2, bellB: Math.PI / 4, bellB2: 3 * Math.PI / 4,
  bellN: [0, 0, 0, 0], bellSum: [0, 0, 0, 0], bellAcc: 0, bellRun: false,
  // Казимир
  casGap: 100e-9,         // зазор, м
  casArea: 1e-4,          // площадь пластин, м² (1 см²)
  // Швингер
  schwField: 1e17,        // поле, В/м
  // туннель
  tunV: 1.0,              // высота барьера, эВ
  tunW: 0.5e-9,           // ширина барьера, м
  tunE: 0.6,              // энергия частицы, эВ
  // общая анимация установок
  t: 0,
};

/** Масса в опыте на текущий момент: M(t) = M₀(1 − t/tисп)^(1/3). */
const evapMass = () => LABS.evapM0 * Math.pow(Math.max(1 - LABS.evapU, 0), 1 / 3);

/* ---------------- расчёты стендов ---------------- */

/** Двухщелевая картина: вероятность попасть в точку экрана по x. */
function slitProfile(x, which) {
  const E = LABS.slitE * PH.e;
  const p = Math.sqrt(2 * PH.me * E);
  const lam = PH.h / p;                       // длина волны де Бройля
  const d = LABS.slitGap, L = 0.35, a = d * 0.28;
  // огибающая от одной щели и интерференция от двух
  const beta = (Math.PI * a * x) / (lam * L);
  const env = beta === 0 ? 1 : (Math.sin(beta) / beta) ** 2;
  if (which) return env;                      // путь измерен — интерференции нет
  const delta = (Math.PI * d * x) / (lam * L);
  return env * Math.cos(delta) ** 2;
}

/** Шаг между полосами, метры. */
function slitSpacing() {
  const p = Math.sqrt(2 * PH.me * LABS.slitE * PH.e);
  return (PH.h / p) * 0.35 / LABS.slitGap;
}

/** Корреляция синглета: E(a,b) = −cos(a−b). */
const bellE = (a, b) => -Math.cos(a - b);

/** Комбинация CHSH по четырём углам. */
function bellCHSH() {
  const { bellA: a, bellA2: a2, bellB: b, bellB2: b2 } = LABS;
  return Math.abs(bellE(a, b) - bellE(a, b2) + bellE(a2, b) + bellE(a2, b2));
}

/** Давление Казимира между идеальными пластинами: P = −π²ħc/(240 d⁴). */
const casimirPressure = (d) => -(Math.PI ** 2 * PH.hbar * PH.c) / (240 * d ** 4);

/** Критическое поле Швингера: E_c = m²c³/(eħ). */
const SCHWINGER_EC = (PH.me ** 2 * PH.c ** 3) / (PH.e * PH.hbar);

/**
 * Число пар в кубометре за секунду, полный ряд Швингера для спинорной КЭД:
 * Γ = (e²E²/4π³ħ²c) Σ 1/n² · exp(−nπE_c/E).
 */
function schwingerRate(E) {
  if (E <= 0) return 0;
  const pref = (PH.e * PH.e * E * E) / (4 * Math.PI ** 3 * PH.hbar ** 2 * PH.c);
  const x = Math.PI * SCHWINGER_EC / E;
  let sum = 0;
  for (let n = 1; n <= 12; n++) sum += Math.exp(-n * x) / (n * n);
  return pref * sum;
}

/* ---------------- горизонт в волокне ---------------- */

/* Кварц: групповой показатель около нуля дисперсии ложится на параболу.
   Отсюда всё и следует: у каждой длины волны есть «зеркальная» пара с той
   же групповой скоростью, и импульс перебрасывает пробу из одной в другую. */
const FIB = {
  lam0: 1270,        // нм, нуль дисперсии кварца
  ng0: 1.4626,       // групповой показатель в этой точке
  beta: 1.276e-7,    // нм⁻², кривизна параболы n_g(λ)
  lamPump: 803,      // нм, накачка (короче нуля дисперсии — тогда она догоняет пробу)
  ePulse: 1e-9,      // Дж, энергия импульса
};

/** Групповой показатель по длине волны, нм → безразмерное. */
const fibNg = (lam) => FIB.ng0 + FIB.beta * (lam - FIB.lam0) ** 2;

/**
 * Что станет с пробой на горизонте. Импульс поднимает показатель на δn,
 * условие горизонта n_g(λ) = n_g(λ_in) + δn даёт вторую, «зазеркальную»
 * ветвь: проба уходит туда, сильно синея.
 */
function fibHorizon() {
  const x = LABS.fibIn - FIB.lam0;
  const shifted = x * x + LABS.fibDn / FIB.beta;
  const out = FIB.lam0 - Math.sqrt(Math.max(shifted, 0)) * Math.sign(x || 1);
  return { lamIn: LABS.fibIn, lamOut: out, ngIn: fibNg(LABS.fibIn) };
}

/** Поверхностная гравитация фронта: κ = c·|Δv_g|/L, м/с². */
function fibKappa() {
  const dv = PH.c * LABS.fibDn / (FIB.ng0 * FIB.ng0);
  return PH.c * dv / LABS.fibEdge;
}

/** Температура Хокинга этого горизонта, К. */
const fibTemp = () => unruhTemp(fibKappa());

/** Энергия одного переброшенного фотона, Дж: её отдаёт импульс. */
function fibQuantum() {
  const h = fibHorizon();
  const wIn = 2 * Math.PI * PH.c / (h.lamIn * 1e-9);
  const wOut = 2 * Math.PI * PH.c / (h.lamOut * 1e-9);
  return PH.hbar * (wOut - wIn);
}

/** Прохождение сквозь прямоугольный барьер. */
function tunnelT(EeV, V0eV, wMeters) {
  const E = EeV * PH.e, V0 = V0eV * PH.e;
  if (E <= 0) return 0;
  if (E < V0) {
    const k = Math.sqrt(2 * PH.me * (V0 - E)) / PH.hbar;
    const sh = Math.sinh(k * wMeters);
    return 1 / (1 + (V0 * V0 * sh * sh) / (4 * E * (V0 - E)));
  }
  if (E === V0) {
    const k = Math.sqrt(2 * PH.me * E) / PH.hbar;
    return 1 / (1 + (k * wMeters) ** 2 / 4);
  }
  const k = Math.sqrt(2 * PH.me * (E - V0)) / PH.hbar;
  const sn = Math.sin(k * wMeters);
  return 1 / (1 + (V0 * V0 * sn * sn) / (4 * E * (E - V0)));
}

/**
 * Кривая Пейджа. Энтропия излучения не может превысить энтропию
 * оставшейся дыры: сначала растёт вместе с потерянной массой, потом
 * идёт по убывающей энтропии горизонта. Излом — момент Пейджа.
 */
function pageCurve(u) {
  // u — доля прожитого времени; M(t) = M0 (1 − u)^(1/3)
  const m = Math.pow(Math.max(1 - u, 0), 1 / 3);
  const sBH = m * m;                       // энтропия дыры в долях начальной
  const sThermal = 1 - sBH;                // грубая энтропия излучения
  return { sBH, sThermal, sRad: Math.min(sThermal, sBH) };
}

/* Момент Пейджа: S_BH падает вдвое при M = M0/√2, то есть при u = 1 − 2^(−3/2). */
const PAGE_TIME = 1 - Math.pow(2, -1.5);   // 0.6464

/* ---------------- геометрия здания ---------------- */

function buildLab() {
  const m = meshBuilder();
  const P = (x, y, z) => {
    const [wx, wz] = LAB.at(x, z);
    return [wx, LAB.y + y, wz];
  };
  const box = (x, y, z, hx, hy, hz, col, ry) => {
    const c = P(x, y, z);
    m.box(c[0], c[1], c[2], hx, hy, hz, LAB.yaw + (ry || 0), col);
  };
  const W = LAB.w, D = LAB.d;
  const conc = [0.80, 0.79, 0.75];
  const concDark = [0.55, 0.55, 0.53];
  const trim = [0.34, 0.36, 0.39];
  const floorCol = [0.52, 0.53, 0.55];
  const line = [0.90, 0.80, 0.32];
  const lampC = [0.92, 0.95, 0.92];

  // плита пола с юбкой, чтобы на склоне не было щели
  box(0, 0.12, 0, W, 0.12, D, floorCol);
  box(0, -0.9, 0, W + 0.1, 0.9, D + 0.1, concDark);
  // разметка прохода и швы плитки
  for (let i = -1; i <= 1; i += 2) box(i * W * 0.66, 0.25, 0, 0.06, 0.01, D * 0.9, line);
  for (let i = -4; i <= 4; i++) box(i * 2.5, 0.245, 0, 0.02, 0.005, D, [0.44, 0.45, 0.47]);
  for (let i = -3; i <= 3; i++) box(0, 0.245, i * 2.5, W, 0.005, 0.02, [0.44, 0.45, 0.47]);

  // посреди прохода — модель той самой дыры, на которую наведён телескоп
  box(0, 0.42, 1.0, 1.15, 0.17, 1.15, concDark, 0.4);
  box(0, 0.60, 1.0, 0.95, 0.04, 0.95, [0.30, 0.31, 0.34], 0.4);
  {
    const c = P(0, 1.28, 1.0);
    m.blob(c[0], c[1], c[2], 0.30, 0.30, 0.30, [0.02, 0.02, 0.03], 14, 9);
    // аккреционный диск: кольцо коротких брусков, наклонённое к проходу
    for (let k = 0; k < 30; k++) {
      const a = (k / 30) * TAU;
      const r = 0.52 + 0.03 * Math.sin(a * 3);
      const hot = 0.55 + 0.45 * Math.sin(a * 2 + 1.0);
      m.box(c[0] + Math.cos(a) * r, c[1] + Math.sin(a) * 0.16, c[2] + Math.sin(a) * r * 0.42,
            0.075, 0.012, 0.075, a, [0.98, 0.55 * hot + 0.28, 0.16 * hot]);
    }
    // стойка под моделью
    m.rope([[c[0], c[1] - 0.30, c[2]], [c[0], LAB.y + 0.62, c[2]]], [0.05, 0.07], [0.30, 0.31, 0.34], 6);
  }

  // стены: задняя, боковые, спереди простенки с проёмом посередине
  box(0, 1.7, D, W, 1.7, 0.18, conc);
  box(-W, 1.7, 0, 0.18, 1.7, D, conc);
  box(W, 1.7, 0, 0.18, 1.7, D, conc);
  box(W * 0.66, 1.7, -D, W * 0.34, 1.7, 0.18, conc);
  // левый простенок с прорезью: сквозь неё телескоп и смотрит на дыру
  {
    const wx = -9.2, hw = 1.1, y0 = 1.15, y1 = 2.55;
    box((-W + (wx - hw)) / 2, 1.7, -D, (wx - hw + W) / 2, 1.7, 0.18, conc);
    box((wx + hw - W * 0.32) / 2, 1.7, -D, (W * 0.32 - wx - hw) / 2, 1.7, 0.18, conc);
    box(wx, y0 / 2, -D, hw, y0 / 2, 0.18, conc);
    box(wx, (y1 + 3.4) / 2, -D, hw, (3.4 - y1) / 2, 0.18, conc);
    // обвязка проёма
    for (const sy of [y0 - 0.06, y1 + 0.06]) box(wx, sy, -D - 0.09, hw + 0.1, 0.06, 0.05, trim);
    for (const sx of [-1, 1]) box(wx + sx * (hw + 0.05), (y0 + y1) / 2, -D - 0.09, 0.05, (y1 - y0) / 2 + 0.12, 0.05, trim);
  }
  box(0, 3.1, -D, W * 0.34, 0.3, 0.18, conc);          // перемычка над входом

  // крыша — только решётка ферм: небо светит внутрь, зал не превращается в погреб
  for (let i = -3; i <= 3; i++) box(i * W / 3.2, 3.5, 0, 0.10, 0.10, D, trim);
  for (let i = -2; i <= 2; i++) box(0, 3.5, i * D / 2.4, W, 0.08, 0.08, trim);
  // карниз по четырём краям, а не крышкой
  box(0, 3.66, -D - 0.15, W + 0.3, 0.12, 0.15, trim);
  box(0, 3.66, D + 0.15, W + 0.3, 0.12, 0.15, trim);
  box(-W - 0.15, 3.66, 0, 0.15, 0.12, D, trim);
  box(W + 0.15, 3.66, 0, 0.15, 0.12, D, trim);

  // подвесные лампы: ночью зал не гаснет
  for (let i = -1; i <= 1; i++) {
    for (const lz of [-4, 0, 4]) {
      box(i * W * 0.55, 3.36, lz, 0.9, 0.05, 0.22, lampC);
      m.rope([P(i * W * 0.55, 3.5, lz), P(i * W * 0.55, 3.41, lz)], [0.02, 0.02], trim, 4);
    }
  }

  // вывеска над входом
  box(0, 3.95, -D - 0.05, 2.5, 0.62, 0.08, [0.13, 0.28, 0.33]);

  // подстанция у западной стены: трансформатор, мачта и провис проводов
  box(-W - 1.9, 0.85, 2.2, 0.9, 0.85, 0.7, concDark);
  for (let i = -2; i <= 2; i++) box(-W - 1.9, 1.5, 2.2 - 0.7 + i * 0.02, 0.86, 0.5, 0.02, [0.30, 0.31, 0.33]);
  for (const pz of [-1.4, 2.2, 5.8]) {
    const a = P(-W - 1.9, 0, pz);
    m.rope([[a[0], terrainH(a[0], a[2]) - 0.2, a[2]], [a[0], LAB.y + 4.2, a[2]]], [0.11, 0.08], trim, 6);
    m.box(a[0], LAB.y + 4.3, a[2], 0.7, 0.06, 0.06, LAB.yaw, trim);
  }
  for (const pair of [[-1.4, 2.2], [2.2, 5.8]]) {
    for (const off of [-0.55, 0.55]) {
      const a = P(-W - 1.9 + off, 4.3, pair[0]), b = P(-W - 1.9 + off, 4.3, pair[1]);
      const nodes = [];
      for (let k = 0; k <= 6; k++) {
        const t = k / 6;
        nodes.push([lerp(a[0], b[0], t), lerp(a[1], b[1], t) - Math.sin(t * Math.PI) * 0.34, lerp(a[2], b[2], t)]);
      }
      m.rope(nodes, nodes.map(() => 0.022), [0.10, 0.10, 0.11], 4);
    }
  }
  // ввод в стену
  {
    const a = P(-W - 1.9, 4.2, 2.2), b = P(-W - 0.2, 2.9, 2.2);
    m.rope([a, [a[0], a[1] - 0.5, a[2]], b], [0.022, 0.022, 0.022], [0.10, 0.10, 0.11], 4);
  }

  // подсобное: шкафы вдоль задней стены и вентиляция на крыше
  for (let i = -2; i <= 2; i++) box(i * 4.4, 1.0, D - 0.7, 1.5, 1.0, 0.45, concDark);
  box(-W * 0.5, 4.0, D * 0.4, 0.7, 0.34, 0.7, trim);
  box(W * 0.5, 4.0, D * 0.4, 0.7, 0.34, 0.7, trim);
  return m.pack();
}

/* ---------------- установки стендов ---------------- */

/* Каждая установка строится в своих координатах: начало на полу,
   лицом к проходу (в −z). */
function buildRigs() {
  const rigs = {};
  const steel = [0.62, 0.63, 0.66];
  const dark = [0.19, 0.20, 0.23];
  const brass = [0.72, 0.58, 0.28];
  const glassC = [0.36, 0.52, 0.58];
  const board = [0.10, 0.13, 0.16];
  const boardLit = [0.30, 0.72, 0.72];

  /** Общий постамент со столешницей и табло. */
  const bench = (m, label) => {
    m.box(0, 0.42, 0, 1.15, 0.42, 0.6, 0, dark);
    m.box(0, 0.88, 0, 1.2, 0.05, 0.66, 0, steel);
    // табло на стойке
    m.rope([[-0.75, 0.9, 0.42], [-0.75, 1.62, 0.5]], [0.035, 0.03], steel, 5);
    m.rope([[0.75, 0.9, 0.42], [0.75, 1.62, 0.5]], [0.035, 0.03], steel, 5);
    m.box(0, 1.72, 0.5, 0.86, 0.30, 0.04, 0, board);
    for (let i = 0; i < 5; i++) {
      m.box(-0.6 + i * 0.3, 1.78 + (i % 2) * 0.06, 0.46, 0.11, 0.018, 0.01, 0,
            i % 2 ? boardLit : [0.20, 0.42, 0.44]);
    }
    m.box(0, 1.60, 0.46, 0.5, 0.02, 0.01, 0, [0.24, 0.50, 0.52]);
  };

  // — испарение: телескоп на вилке. Труба живёт отдельным мешем: каждый
  //   кадр её доворачивают на дыру, поэтому в общий постамент она не входит.
  {
    const m = meshBuilder();
    bench(m);
    m.rope([[-0.34, 0.93, 0], [-0.34, 1.36, 0]], [0.10, 0.09], steel, 7);
    m.rope([[0.34, 0.93, 0], [0.34, 1.36, 0]], [0.10, 0.09], steel, 7);
    m.box(0, 1.36, 0, 0.42, 0.05, 0.09, 0, dark);                 // ось вилки
    rigs.evap = m.pack();

    const t = meshBuilder();
    // труба построена вдоль +z: окуляр сзади, объектив впереди
    t.rope([[0, 0, -0.30], [0, 0, 0.50]], [0.115, 0.135], [0.30, 0.32, 0.36], 12);
    t.rope([[0, 0, 0.50], [0, 0, 0.64]], [0.145, 0.140], dark, 12);
    t.blob(0, 0, 0.50, 0.115, 0.115, 0.02, glassC, 12, 5);        // объектив
    t.blob(0, 0, -0.34, 0.05, 0.05, 0.06, dark, 10, 5);           // окуляр
    t.rope([[0, 0.16, 0.02], [0, 0.16, 0.26]], [0.032, 0.030], brass, 6);   // искатель
    t.box(0, 0.09, 0.14, 0.02, 0.06, 0.14, 0, dark);
    // хомут на оси вилки
    t.box(0, 0, 0, 0.20, 0.075, 0.075, 0, dark);
    rigs.evapScope = t.pack();
  }
  // — кривая Пейджа: планшет с графиком на наклонной стойке
  {
    const m = meshBuilder();
    bench(m);
    m.box(0, 1.24, -0.1, 0.62, 0.42, 0.03, 0, board);
    m.box(0, 1.24, -0.12, 0.56, 0.36, 0.01, 0, [0.06, 0.10, 0.12]);
    m.rope([[0, 0.93, 0.16], [0, 1.24, 0.02]], [0.05, 0.04], steel, 6);
    // «перо» самописца
    m.rope([[-0.2, 1.30, -0.16], [0.24, 1.18, -0.16]], [0.012, 0.008], [0.85, 0.30, 0.25], 4);
    rigs.page = m.pack();
  }
  // — волокно: катушка, лазер накачки, спектрометр
  {
    const m = meshBuilder();
    bench(m);
    // катушка волокна
    for (let i = 0; i < 3; i++) {
      const nodes = [];
      for (let k = 0; k <= 22; k++) {
        const a = (k / 22) * TAU;
        nodes.push([Math.cos(a) * (0.30 + i * 0.035), 0.95 + i * 0.02, 0.05 + Math.sin(a) * (0.30 + i * 0.035)]);
      }
      m.rope(nodes, nodes.map(() => 0.014), [0.85, 0.86, 0.30], 4);
    }
    m.box(-0.78, 1.02, -0.05, 0.20, 0.10, 0.14, 0, dark);        // лазер
    m.box(-0.60, 1.02, -0.05, 0.03, 0.03, 0.03, 0, [1.0, 0.35, 0.25]);
    m.box(0.78, 1.06, -0.05, 0.22, 0.14, 0.18, 0, steel);        // спектрометр
    m.box(0.78, 1.20, -0.05, 0.16, 0.02, 0.12, 0, boardLit);
    rigs.fiber = m.pack();
  }
  // — двухщелевой: пушка, диафрагма, экран
  {
    const m = meshBuilder();
    bench(m);
    m.rope([[0, 1.02, 0.5], [0, 1.02, 0.16]], [0.09, 0.07], dark, 8);   // пушка
    m.box(0, 1.02, 0.0, 0.42, 0.30, 0.02, 0, [0.30, 0.31, 0.34]);       // диафрагма
    for (const sx of [-1, 1]) m.box(sx * 0.05, 1.02, -0.002, 0.012, 0.12, 0.012, 0, [0.02, 0.02, 0.03]);
    m.box(0, 1.10, -0.5, 0.52, 0.34, 0.02, 0, [0.08, 0.09, 0.11]);      // экран
    m.rope([[0, 0.93, -0.5], [0, 0.78, -0.5]], [0.03, 0.03], steel, 5);
    rigs.slit = m.pack();
  }
  // — Белл: источник в центре, два детектора на поворотных плечах
  {
    const m = meshBuilder();
    bench(m);
    m.blob(0, 1.06, 0, 0.11, 0.11, 0.11, [0.30, 0.34, 0.42], 10, 6);
    m.blob(0, 1.06, 0, 0.055, 0.055, 0.055, [0.55, 0.85, 0.95], 8, 5);
    for (const sx of [-1, 1]) {
      m.rope([[sx * 0.12, 1.06, 0], [sx * 0.72, 1.06, 0]], [0.016, 0.012], [0.60, 0.75, 0.85], 4);
      m.box(sx * 0.86, 1.06, 0, 0.13, 0.11, 0.11, 0, dark);
      m.box(sx * 0.86, 1.20, 0, 0.05, 0.03, 0.05, 0, boardLit);
    }
    rigs.bell = m.pack();
  }
  // — Казимир: две пластины на микрометрическом столике
  {
    const m = meshBuilder();
    bench(m);
    m.box(-0.26, 1.16, 0, 0.02, 0.24, 0.24, 0, [0.78, 0.79, 0.82]);
    m.box(0.26, 1.16, 0, 0.02, 0.24, 0.24, 0, [0.78, 0.79, 0.82]);
    m.rope([[-0.26, 1.42, 0], [-0.26, 0.93, 0]], [0.02, 0.02], steel, 5);
    m.rope([[0.26, 1.42, 0], [0.26, 0.93, 0]], [0.02, 0.02], steel, 5);
    // микрометр и стрелка динамометра
    m.rope([[0.62, 1.16, 0], [0.30, 1.16, 0]], [0.035, 0.03], brass, 6);
    m.box(-0.72, 1.30, 0, 0.16, 0.16, 0.03, 0, board);
    m.box(-0.72, 1.30, -0.02, 0.01, 0.11, 0.01, 0.5, [0.90, 0.35, 0.28]);
    rigs.casimir = m.pack();
  }
  // — Швингер: конденсатор с высоковольтными вводами
  {
    const m = meshBuilder();
    bench(m);
    m.box(0, 1.16, -0.18, 0.44, 0.30, 0.02, 0, [0.80, 0.72, 0.40]);
    m.box(0, 1.16, 0.18, 0.44, 0.30, 0.02, 0, [0.80, 0.72, 0.40]);
    for (const sz of [-1, 1]) {
      for (let i = 0; i < 3; i++) {
        m.blob(0, 1.52 + i * 0.10, sz * 0.18, 0.09 - i * 0.015, 0.05, 0.09 - i * 0.015, [0.86, 0.88, 0.90], 8, 4);
      }
      m.rope([[0, 1.46, sz * 0.18], [0, 1.30, sz * 0.18]], [0.02, 0.02], steel, 5);
    }
    rigs.schwinger = m.pack();
  }
  // — туннелирование: волновод с барьером и рядом туннельный микроскоп
  {
    const m = meshBuilder();
    bench(m);
    // волновод, по которому бежит волна (её рисуют точками поверх)
    m.box(-0.15, 1.00, 0, 0.86, 0.02, 0.15, 0, [0.26, 0.28, 0.32]);
    m.box(-0.15, 1.075, 0, 0.045, 0.13, 0.155, 0, [0.55, 0.30, 0.62]);   // барьер
    m.box(-0.98, 1.06, 0, 0.09, 0.08, 0.09, 0, dark);                 // пушка
    m.box(0.68, 1.06, 0, 0.09, 0.08, 0.09, 0, dark);                  // счётчик
    m.box(0.68, 1.17, 0, 0.05, 0.03, 0.05, 0, boardLit);

    // микроскоп: стол на пружинах, колпак, пьезотрубка с остриём
    const mx = 0.88;
    m.box(mx, 0.95, 0, 0.26, 0.03, 0.22, 0, [0.34, 0.35, 0.38]);      // виброразвязка
    for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
      const nodes = [];
      for (let k = 0; k <= 8; k++) {
        const a = (k / 8) * TAU * 2.5;
        nodes.push([mx + sx * 0.19 + Math.cos(a) * 0.022, 0.91 + k * 0.006, sz * 0.15 + Math.sin(a) * 0.022]);
      }
      m.rope(nodes, nodes.map(() => 0.009), steel, 4);
    }
    m.box(mx, 1.00, 0, 0.20, 0.02, 0.16, 0, [0.72, 0.60, 0.30]);      // образец
    // пьезотрубка и остриё
    m.rope([[mx, 1.36, 0], [mx, 1.10, 0]], [0.055, 0.035], [0.30, 0.31, 0.35], 8);
    m.rope([[mx, 1.10, 0], [mx, 1.028, 0]], [0.020, 0.002], [0.86, 0.88, 0.92], 6);
    // кронштейн и колпак
    m.box(mx + 0.24, 1.20, 0, 0.03, 0.24, 0.10, 0, steel);
    m.box(mx, 1.42, 0, 0.24, 0.02, 0.20, 0, steel);
    for (const sx of [-1, 1]) m.rope([[mx + sx * 0.22, 1.42, 0], [mx + sx * 0.22, 0.98, 0]], [0.012, 0.012], [0.42, 0.48, 0.52], 5);
    // маленький экран микроскопа с картинкой скана
    m.box(mx - 0.02, 1.30, 0.30, 0.17, 0.12, 0.02, 0.35, board);
    for (let i = 0; i < 4; i++) {
      m.box(mx - 0.02 + (i - 1.5) * 0.075, 1.30, 0.28, 0.028, 0.085, 0.005, 0.35,
            [0.95, 0.55 + 0.12 * (i % 2), 0.20]);
    }
    rigs.tunnel = m.pack();
  }
  return rigs;
}

/* ---------------- вывод чисел ---------------- */

const SUP = { '-': '⁻', 0: '⁰', 1: '¹', 2: '²', 3: '³',
  4: '⁴', 5: '⁵', 6: '⁶', 7: '⁷', 8: '⁸', 9: '⁹' };

/** Показатель степени надстрочными знаками. */
const sup = (n) => String(n).split('').map((c) => SUP[c] || c).join('');

/** Число с нужным числом значащих цифр: близкие — как есть, далёкие — степенью. */
function sci(v, d = 3) {
  if (!isFinite(v)) return v > 0 ? '∞' : '−∞';
  if (v === 0) return '0';
  const s = v < 0 ? '−' : '';
  const a = Math.abs(v);
  const e = Math.floor(Math.log10(a));
  if (e >= -3 && e < 5) {
    const t = a.toFixed(Math.max(0, d - 1 - e));
    return s + (t.indexOf('.') >= 0 ? t.replace(/0+$/, '').replace(/\.$/, '') : t);
  }
  const mant = (a / Math.pow(10, e)).toFixed(d - 1).replace(/0+$/, '').replace(/\.$/, '');
  return s + (mant === '1' ? '10' : mant + '·' + '10') + sup(e);
}

/** Промежуток времени в человеческих единицах. */
function dur(sec) {
  if (!isFinite(sec)) return '∞';
  if (sec < 1e-9) return sci(sec) + ' с';
  if (sec < 90) return sci(sec, 3) + ' с';
  if (sec < 5400) return (sec / 60).toFixed(1) + ' мин';
  if (sec < 1.7e5) return (sec / 3600).toFixed(1) + ' ч';
  if (sec < 3e7) return (sec / 86400).toFixed(1) + ' сут';
  return sci(sec / PH.year, 3) + ' лет';
}

/* ============================================================
   Туннелирование: пакет, который видно
   ------------------------------------------------------------
   Уравнение Шрёдингера решается прямо в кадре, на сетке.
   Единицы удобные: нанометры, фемтосекунды, электронвольты —
   тогда ħ и масса электрона становятся числами порядка единицы.
   ============================================================ */

const QM = {
  hbar: 0.6582119569,     // эВ·фс
  me: 5.6856301,          // эВ·фс²/нм² — это m_e, пересчитанная из m_ec² = 511 кэВ
};

/* Сетка и состояние пакета. Схема шага — полунеявная (Висшер):
   сначала двигаем действительную часть по мнимой, потом мнимую по
   уже новой действительной. Она сохраняет норму и устойчива,
   пока dt < 2ħ/‖H‖. */
const WP = {
  N: 440, xa: -8, xb: 8,           // нм
  dx: 0, dt: 0.008,                // фс
  re: null, im: null, V: null, mask: null,
  t: 0, run: false, launched: false, loop: false,
  // пакет намеренно длинный: чем он длиннее, тем уже полоса энергий и тем
  // ближе измеренная доля к формуле для одной энергии
  sig: 1.35, start: -5.0,          // ширина и место старта пакета, нм
  left: 0, inside: 0, right: 0,    // куда разошлась вероятность
  key: '',
};

function wpAlloc() {
  WP.dx = (WP.xb - WP.xa) / (WP.N - 1);
  WP.re = new Float64Array(WP.N);
  WP.im = new Float64Array(WP.N);
  WP.V = new Float64Array(WP.N);
  WP.mask = new Float64Array(WP.N);
  for (let i = 0; i < WP.N; i++) {
    // мягкая кайма по краям: пакет уходит и не отражается от границы сетки
    const e = Math.min(i, WP.N - 1 - i) / (WP.N * 0.10);
    WP.mask[i] = e >= 1 ? 1 : 0.5 - 0.5 * Math.cos(Math.PI * clamp(e, 0, 1));
  }
}

const wpX = (i) => WP.xa + i * WP.dx;
/** Полуширина барьера в нанометрах. */
const wpHalf = () => LABS.tunW * 1e9 / 2;

function wpPotential() {
  const h = wpHalf();
  for (let i = 0; i < WP.N; i++) WP.V[i] = Math.abs(wpX(i)) <= h ? LABS.tunV : 0;
}

/** Заново собрать гауссов пакет со средней энергией E. */
function wpReset() {
  if (!WP.re) wpAlloc();
  wpPotential();
  const k = Math.sqrt(2 * QM.me * LABS.tunE) / QM.hbar;     // нм⁻¹
  const s = WP.sig;
  let norm = 0;
  for (let i = 0; i < WP.N; i++) {
    const x = wpX(i);
    const g = Math.exp(-((x - WP.start) ** 2) / (2 * s * s));
    WP.re[i] = g * Math.cos(k * x);
    WP.im[i] = g * Math.sin(k * x);
    norm += g * g;
  }
  norm = Math.sqrt(norm * WP.dx) || 1;
  for (let i = 0; i < WP.N; i++) { WP.re[i] /= norm; WP.im[i] /= norm; }
  WP.t = 0;
  WP.launched = false;
  // шаг по времени держим с запасом от предела устойчивости
  const kin = (QM.hbar * QM.hbar) / (2 * QM.me * WP.dx * WP.dx);
  WP.dt = 0.35 * QM.hbar / (4 * kin + LABS.tunV);
  // опыт заканчиваем, когда прошедшая часть добежала до края, но кайма её
  // ещё не съела: тогда слева ровно отражённое, справа ровно прошедшее
  const v = (QM.hbar * k) / QM.me;                       // нм/фс
  WP.tEnd = clamp((Math.abs(WP.start) + 6.4) / v * 1.05, 3, 120);
  WP.key = wpKey();
  WP.scale = 0;
  wpTally();
  WP.scale = 0;
  for (let i = 0; i < WP.N; i++) WP.scale = Math.max(WP.scale, wpDens(i));
}

/** По чему понятно, что настройки сменились и пакет надо пересобрать. */
const wpKey = () => LABS.tunE.toFixed(4) + '|' + LABS.tunV.toFixed(4) + '|' + LABS.tunW.toExponential(4);

/** n шагов по времени. */
function wpStep(n) {
  const { re, im, V, mask, dx, dt, N } = WP;
  const c = (QM.hbar * dt) / (2 * QM.me * dx * dx);
  const d = dt / QM.hbar;
  for (let s = 0; s < n; s++) {
    // Re += dt/ħ · H·Im
    for (let i = 1; i < N - 1; i++) {
      re[i] += -c * (im[i + 1] - 2 * im[i] + im[i - 1]) + d * V[i] * im[i];
    }
    // Im -= dt/ħ · H·Re, уже по новой Re
    for (let i = 1; i < N - 1; i++) {
      im[i] -= -c * (re[i + 1] - 2 * re[i] + re[i - 1]) + d * V[i] * re[i];
    }
    for (let i = 0; i < N; i++) { re[i] *= mask[i]; im[i] *= mask[i]; }
    WP.t += dt;
  }
  wpTally();
}

/** Сколько вероятности слева от барьера, внутри и справа. */
function wpTally() {
  const h = wpHalf();
  let l = 0, c = 0, r = 0;
  for (let i = 0; i < WP.N; i++) {
    const p = WP.re[i] * WP.re[i] + WP.im[i] * WP.im[i];
    const x = wpX(i);
    if (x < -h) l += p; else if (x > h) r += p; else c += p;
  }
  const k = WP.dx;
  const tot = (l + c + r) * k || 1;
  // доли считаем от того, что ещё на сетке: кайма по краям понемногу гасит волну
  WP.left = l * k / tot; WP.inside = c * k / tot; WP.right = r * k / tot;
  WP.norm = tot;
}

/** Полоса энергий пакета: ΔE = ħ²k·Δk/m при Δk = 1/(2σ). */
function wpSpread() {
  const k = Math.sqrt(2 * QM.me * LABS.tunE) / QM.hbar;
  return (QM.hbar * QM.hbar * k) / (2 * QM.me * WP.sig);
}

/** Плотность в точке сетки (для картинки и для точек на стенде). */
const wpDens = (i) => WP.re[i] * WP.re[i] + WP.im[i] * WP.im[i];

/* ---------------- туннельный микроскоп ---------------- */

const STM = {
  gap: 0.55,        // нм между остриём и образцом
  phi: 4.5,         // работа выхода, эВ
  bias: 0.10,       // напряжение на промежутке, В
  scan: 0,          // где сейчас идёт строчка, 0..1
  corr: 0.048,      // амплитуда атомного рельефа, нм
  a: 0.246,         // постоянная решётки графита, нм
  canvas: null, ctx: null, key: '',
};

/** Постоянная затухания под барьером работы выхода, нм⁻¹. */
const stmKappa = () => Math.sqrt(2 * QM.me * STM.phi) / QM.hbar;

/** Ток при зазоре d: I ∝ V·exp(−2κd). Нормирован на 1 нА при 0,5 нм. */
function stmCurrent(d) {
  const k = stmKappa();
  return (STM.bias / 0.10) * Math.exp(-2 * k * (d - 0.5));
}

/** Пересчитать картинку скана. Дёргается только когда меняется работа выхода. */
function stmImage(W, H, spanX, spanY) {
  const key = W + 'x' + H + '|' + STM.phi.toFixed(3);
  if (STM.key === key) return STM.canvas;
  if (!STM.canvas) {
    STM.canvas = document.createElement('canvas');
    STM.ctx = STM.canvas.getContext('2d');
  }
  STM.canvas.width = W; STM.canvas.height = H;
  const g = STM.ctx;
  const img = g.createImageData(W, H);
  const k = stmKappa();
  const val = new Float32Array(W * H);
  let lo = 1e9, hi = -1e9;
  for (let j = 0; j < H; j++) {
    const y = (j / H - 0.5) * spanY;
    for (let i = 0; i < W; i++) {
      const x = (i / W - 0.5) * spanX;
      const v = 2 * k * stmHeight(x, y);            // логарифм относительного тока
      val[j * W + i] = v;
      if (v < lo) lo = v;
      if (v > hi) hi = v;
    }
  }
  const rng = Math.max(hi - lo, 1e-6);
  for (let n = 0; n < W * H; n++) {
    const t = (val[n] - lo) / rng;
    const q = n * 4;
    img.data[q] = 26 + 229 * Math.pow(t, 0.85);
    img.data[q + 1] = 12 + 176 * Math.pow(t, 1.25);
    img.data[q + 2] = 8 + 96 * Math.pow(t, 2.1);
    img.data[q + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  STM.key = key;
  return STM.canvas;
}

/** Высота поверхности: три волны под 120° дают треугольную решётку. */
function stmHeight(x, y) {
  const b = (4 * Math.PI) / (STM.a * Math.sqrt(3));
  let h = 0;
  for (let n = 0; n < 3; n++) {
    const a = (n * TAU) / 3;
    h += Math.cos(b * (x * Math.cos(a) + y * Math.sin(a)));
  }
  return (h / 3) * STM.corr;
}

/* ---------------- панели стендов ---------------- */

/* Каждая панель: формула, объяснение своими словами, живые числа,
   график и органы управления. Числа считаются тут же по формулам сверху,
   ничего не подставлено руками. */

const CY = '#2fd6c8', RU = '#e0763f', WH = 'rgba(244,234,217,0.9)';

/** Рамка графика: сетка и подписи осей. */
function plotFrame(g, W, H, xl, yl) {
  g.clearRect(0, 0, W, H);
  g.fillStyle = 'rgba(6,10,12,0.78)';
  g.fillRect(0, 0, W, H);
  g.strokeStyle = 'rgba(244,234,217,0.13)';
  g.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = 12 + (H - 34) * i / 4;
    g.beginPath(); g.moveTo(34, y); g.lineTo(W - 8, y); g.stroke();
  }
  for (let i = 0; i <= 4; i++) {
    const x = 34 + (W - 42) * i / 4;
    g.beginPath(); g.moveTo(x, 12); g.lineTo(x, H - 22); g.stroke();
  }
  g.fillStyle = 'rgba(244,234,217,0.5)';
  g.font = '10px ui-sans-serif, Arial, sans-serif';
  g.textAlign = 'right'; g.textBaseline = 'alphabetic';
  if (xl) { g.textAlign = 'right'; g.fillText(xl, W - 10, H - 8); }
  if (yl) { g.textAlign = 'left'; g.fillText(yl, 6, 10); }
}

/** Кривая по функции от доли ширины. */
function plotCurve(g, W, H, f, color, dash) {
  g.strokeStyle = color; g.lineWidth = 1.6;
  g.setLineDash(dash || []);
  g.beginPath();
  let started = false;
  for (let i = 0; i <= 160; i++) {
    const t = i / 160;
    const v = f(t);
    if (!isFinite(v)) { started = false; continue; }
    const x = 34 + (W - 42) * t;
    const y = 12 + (H - 34) * (1 - clamp(v, 0, 1));
    if (started) g.lineTo(x, y); else { g.moveTo(x, y); started = true; }
  }
  g.stroke();
  g.setLineDash([]);
}

/** Вертикальная отметка «мы здесь». */
function plotMark(g, W, H, t, color, text) {
  const x = 34 + (W - 42) * clamp(t, 0, 1);
  g.strokeStyle = color; g.lineWidth = 1; g.setLineDash([3, 3]);
  g.beginPath(); g.moveTo(x, 12); g.lineTo(x, H - 22); g.stroke();
  g.setLineDash([]);
  if (text) {
    g.fillStyle = color; g.font = '10px ui-sans-serif, Arial, sans-serif';
    g.textAlign = x > W * 0.6 ? 'right' : 'left';
    g.fillText(text, x + (x > W * 0.6 ? -4 : 4), 22);
  }
}

const PANELS = {

  /* — испарение чёрной дыры — */
  evap: {
    why: [
      'Поле у горизонта раскладывается по модам двумя разными способами: так, как это делает падающий наблюдатель, и так, как далёкий. Преобразование Боголюбова между ними смешивает положительные и отрицательные частоты, и вакуум первого оказывается для второго тепловой ванной с T = ħκ/(2πck_B), где κ = c⁴/(4GM) — поверхностная гравитация горизонта. Подставив κ, получаем формулу температуры. Дальше как у нагретого тела: P = σT⁴·4πrₛ², и с rₛ = 2GM/c² всё складывается в ħc⁶/(15360πG²M²). Остаётся dM/dt = −P/c², то есть M²dM = −const·dt, откуда M(t) = M₀(1 − t/tисп)^(1/3) и кубический закон для времени жизни.',
      'Считается одно безмассовое поле и чистая геометрическая оптика вместо серых коэффициентов: настоящий поток заметно больше и скачками растёт, когда температура дорастает до массы очередной частицы. Дыра без вращения и заряда. Формула для убывания массы верна, только пока вокруг холоднее, чем дыра, — наша поглощает реликтовый фон быстрее, чем светит, и на самом деле растёт. Последние планковские массы теория не описывает вовсе: там нужна квантовая гравитация, и «вспышка в конце» — экстраполяция.',
    ],
    formula: 'T = ħc³ / (8πGMk<sub>B</sub>)    '
      + 'P = ħc⁶ / (15360πG²M²)    '
      + 't<sub>исп</sub> = 5120πG²M³ / (ħc⁴)',
    note: 'Горизонт светится как нагретое тело, и чем легче дыра, тем она горячее: температура идёт как 1/M. '
      + 'Поэтому испарение разгоняет само себя: масса убывает как (1−t/tисп)^(1/3), и последние тонны уходят вспышкой. '
      + 'Дыра с этого полигона холоднее реликтового фона и пока не испаряется, а растёт — чтобы увидеть испарение, её надо облегчить.',
    ctl: [
      { k: 'sl', label: 'Масса', min: 4, max: 31, step: 0.02, log: true,
        get: () => LABS.evapM0,
        set: (v) => { LABS.evapM0 = v; LABS.evapU = 0; LABS.evapRun = false; },
        fmt: (v) => sci(v) + ' кг' },
      { k: 'sl', label: 'Прожито', min: 0, max: 0.999999, step: 1e-6,
        get: () => LABS.evapU,
        set: (v) => { LABS.evapU = v; LABS.evapRun = false; },
        fmt: (v) => (v * 100).toFixed(4) + ' %' },
      { k: 'bt', label: () => LABS.evapRun ? 'Остановить' : 'Прокрутить жизнь',
        on: () => {
          if (LABS.evapU > 0.99999) { LABS.evapU = 0; LABS.evapGone = false; }
          LABS.evapRun = !LABS.evapRun;
        } },
      { k: 'tg', label: 'Связать с дырой за стеной',
        get: () => LABS.evapLive,
        set: (v) => {
          LABS.evapLive = v; LABS.evapNote = '';
          if (v) { LABS.evapGone = false; bhSetMass(evapMass()); } else bhRestore();
        } },
      { k: 'bt', label: () => 'Сброс',
        on: () => {
          LABS.evapU = 0; LABS.evapRun = false; LABS.evapGone = false; LABS.evapNote = '';
          LABS.evapM0 = BH_M0;
          if (LABS.evapLive) bhSetMass(BH_M0); else bhRestore();
        } },
    ],
    read: () => {
      const M = evapMass();
      const tau = bhLife(LABS.evapM0);
      const T = bhTemp(M), P = bhPower(M);
      const rows = [
        ['масса сейчас', sci(M) + ' кг'],
        ['горизонт rₛ', sci(bhRadius(M)) + ' м'],
        ['температура', sci(T) + ' К'],
        ['мощность', sci(P) + ' Вт'],
        ['энтропия S/k<sub>B</sub>', sci(bhEntropy(M))],
        ['полная жизнь', dur(tau)],
        ['прошло', dur(tau * LABS.evapU)],
        ['осталось', dur(bhLife(M))],
        [T > PH.Tcmb ? 'горячее реликта в' : 'холоднее реликта в',
          sci(T > PH.Tcmb ? T / PH.Tcmb : PH.Tcmb / T) + ' раз'],
      ];
      if (LABS.evapLive) {
        const a = bhAngle();
        rows.push(['дыра за стеной', LABS.evapGone ? 'испарилась' : sci(BH.rs, 3) + ' м']);
        rows.push(['её тень отсюда', a * 57.29578 < 0.017 ? 'меньше минуты дуги'
          : (a * 57.29578).toFixed(2) + '°']);
        rows.push(['ваши часы медленнее в', game.dilation.toFixed(3) + ' раз']);
      }
      if (LABS.evapNote) rows.push(['связь', LABS.evapNote]);
      return rows;
    },
    plot: (g, W, H) => {
      plotFrame(g, W, H, 't / tисп', 'M/M₀ и lg T');
      plotCurve(g, W, H, (t) => Math.pow(Math.max(1 - t, 0), 1 / 3), CY);
      // температура растёт как 1/M: показываем логарифм в пределах шести порядков
      const T0 = bhTemp(LABS.evapM0);
      plotCurve(g, W, H, (t) => {
        const M = LABS.evapM0 * Math.pow(Math.max(1 - t, 1e-18), 1 / 3);
        return clamp(Math.log10(bhTemp(M) / T0) / 6, 0, 1);
      }, RU, [4, 3]);
      plotMark(g, W, H, LABS.evapU, WH, null);
      g.font = '10px ui-sans-serif, Arial, sans-serif'; g.textAlign = 'left';
      g.fillStyle = CY; g.fillText('масса', 40, 26);
      g.fillStyle = RU; g.fillText('температура', 40, H - 30);
    },
  },

  /* — кривая Пейджа — */
  page: {
    why: [
      'Энтропия запутывания части системы не может превысить логарифм размерности меньшей из частей. Пока излучения мало, меньшее — оно само, и его энтропия растёт почти как тепловая. Когда дыра усохла, потолком становится уже её энтропия S = 4πGM²/(ħc), и дальше кривая обязана идти вниз вместе с M². Обе ветви равны там, где энтропия горизонта упала вдвое, то есть при M = M₀/√2; подставив M(t) = M₀(1 − t/tисп)^(1/3), получаем t/tисп = 1 − 2^(−3/2) ≈ 0,6464.',
      'Всё держится на предположении, что испарение унитарно и информация в принципе возвращается, — это гипотеза, а не измеренный факт. Дыра считается системой с конечным числом состояний e^S. Излом нарисован острым: у Пейджа он сглажен на масштабе одной-двух единиц энтропии, а вблизи конца испарения форма зависит от модели (островные вклады, репличные червоточины).',
    ],
    formula: 'S<sub>дыры</sub>/k<sub>B</sub> = 4πGM²/(ħc)   M(t) = M₀(1−t/t<sub>исп</sub>)<sup>1/3</sup>   '
      + 't<sub>Пейджа</sub> = (1−2<sup>−3/2</sup>)·t<sub>исп</sub> ≈ 0,6464·t<sub>исп</sub>',
    note: 'Сколько информации унесло излучение? Если считать его просто тепловым, энтропия растёт до самого конца — '
      + 'и тогда информация теряется. Но энтропия запутывания не может превысить энтропию того, с чем запутано, '
      + 'а дыра усыхает. Ломаная точка — момент Пейджа: с него излучение начинает отдавать информацию обратно.',
    ctl: [
      { k: 'sl', label: 'Момент', min: 0, max: 1, step: 0.001,
        get: () => LABS.pageU, set: (v) => { LABS.pageU = v; },
        fmt: (v) => (v * 100).toFixed(1) + ' % жизни' },
      { k: 'bt', label: () => 'В точку Пейджа', on: () => { LABS.pageU = PAGE_TIME; } },
    ],
    read: () => {
      const p = pageCurve(LABS.pageU);
      const M = LABS.evapM0 * Math.pow(Math.max(1 - LABS.pageU, 0), 1 / 3);
      const S0 = bhEntropy(LABS.evapM0);
      return [
        ['энтропия дыры', sci(bhEntropy(M)) + ' k' + sup('B')],
        ['в долях начальной', (p.sBH * 100).toFixed(1) + ' %'],
        ['тепловая оценка излучения', (p.sThermal * 100).toFixed(1) + ' %'],
        ['что на самом деле', (p.sRad * 100).toFixed(1) + ' %'],
        ['максимум кривой', sci(S0 / 2) + ' k' + sup('B')],
        ['точка Пейджа', (PAGE_TIME * 100).toFixed(2) + ' % жизни'],
        ['её время для этой дыры', dur(bhLife(LABS.evapM0) * PAGE_TIME)],
      ];
    },
    plot: (g, W, H) => {
      plotFrame(g, W, H, 't / tисп', 'S / S₀');
      plotCurve(g, W, H, (t) => pageCurve(t).sBH, RU, [4, 3]);
      plotCurve(g, W, H, (t) => pageCurve(t).sThermal, 'rgba(244,234,217,0.35)', [2, 3]);
      plotCurve(g, W, H, (t) => pageCurve(t).sRad, CY);
      plotMark(g, W, H, PAGE_TIME, 'rgba(244,234,217,0.6)', 'Пейдж');
      plotMark(g, W, H, LABS.pageU, WH, null);
    },
  },

  /* — горизонт в оптическом волокне — */
  fiber: {
    why: [
      'В системе отсчёта, бегущей вместе с импульсом, картина статична: есть область с поднятым показателем преломления и точка, где групповая скорость пробы сравнивается со скоростью импульса. Пройти её проба не может — это и есть горизонт. Сохраняется частота, измеренная в этой системе, а она связывает n_g на входе и выходе: n_g(λвых) = n_g(λвх) + δn. Около нуля дисперсии n_g(λ) — парабола, поэтому у уравнения два корня, и проба перескакивает с длинноволновой ветви на коротковолновую. Температура оценивается как для любого горизонта: T = ħκ/(2πck_B), где κ = c·Δv/L — насколько круто меняется скорость на фронте.',
      'Дисперсия взята параболой: у настоящего кварца кривая сложнее, и вдали от λ₀ ответ поедет. Нелинейность сведена к постоянной ступеньке δn — ни самофазовой модуляции, ни солитонной динамики. Потери, рамановское рассеяние и поляризация не учтены. κ оценена по порядку величины: точное значение зависит от формы фронта. И главное — аналог воспроизводит кинематику горизонта, но не гравитацию: никакой настоящей кривизны тут нет.',
    ],
    formula: 'n<sub>g</sub>(λ) = n₀ + β(λ−λ₀)²   '
      + 'горизонт: n<sub>g</sub>(λвых) = n<sub>g</sub>(λвх) + δn   '
      + 'T = ħκ/(2πck<sub>B</sub>), κ = c·Δv/L',
    note: 'Световой импульс в волокне поднимает показатель преломления и тащит эту ступеньку за собой. '
      + 'Для пробного луча её фронт — горизонт: догнать нельзя, можно только отразиться, перепрыгнув на другую ветвь дисперсии — то есть резко посинев. '
      + 'Температура такого горизонта мизерна, поэтому самопроизвольное излучение не поймать; ловят вынужденное — и отдачу: '
      + 'каждый посиневший фотон берёт энергию у самого импульса, и тот краснеет.',
    ctl: [
      { k: 'sl', label: 'Ступенька δn', min: 1e-4, max: 4e-3, step: 1e-5,
        get: () => LABS.fibDn, set: (v) => { LABS.fibDn = v; }, fmt: (v) => sci(v, 2) },
      { k: 'sl', label: 'Проба λвх', min: 1300, max: 1700, step: 1,
        get: () => LABS.fibIn, set: (v) => { LABS.fibIn = v; }, fmt: (v) => v.toFixed(0) + ' нм' },
      { k: 'sl', label: 'Фронт L', min: 0.3e-6, max: 8e-6, step: 0.1e-6,
        get: () => LABS.fibEdge, set: (v) => { LABS.fibEdge = v; },
        fmt: (v) => (v * 1e6).toFixed(1) + ' мкм' },
      { k: 'bt', label: () => LABS.fibOn ? 'Накачка идёт' : 'Включить накачку',
        on: () => { LABS.fibOn = !LABS.fibOn; } },
      { k: 'bt', label: () => 'Сброс счёта', on: () => { LABS.fibN = 0; } },
    ],
    read: () => {
      const h = fibHorizon();
      const T = fibTemp();
      const dE = fibQuantum();
      const nPump = FIB.ePulse / (PH.hbar * 2 * Math.PI * PH.c / (FIB.lamPump * 1e-9));
      const lost = LABS.fibN * dE;
      const rel = lost / FIB.ePulse;
      return [
        ['групповой n<sub>g</sub> на входе', h.ngIn.toFixed(5)],
        ['проба на выходе', h.lamOut.toFixed(1) + ' нм'],
        ['сдвиг частоты', sci((PH.c / (h.lamOut * 1e-9) - PH.c / (h.lamIn * 1e-9)) / 1e12, 3) + ' ТГц'],
        ['κ горизонта', sci(fibKappa()) + ' м/с²'],
        ['температура Хокинга', sci(T) + ' К'],
        ['квант отдачи', sci(dE) + ' Дж'],
        ['фотонов в импульсе', sci(nPump)],
        ['переброшено', sci(LABS.fibN, 4)],
        ['импульс отдал', sci(lost) + ' Дж (' + sci(rel * 100, 2) + ' %)'],
        ['накачка покраснела на', sci(FIB.lamPump * rel * 1e6, 3) + ' пм'],
      ];
    },
    plot: (g, W, H) => {
      plotFrame(g, W, H, 'λ, нм', 'n' + 'ᵧ'.replace('ᵧ', 'g') + '(λ)');
      const lo = 700, hi = 1800;
      const ngLo = FIB.ng0, ngHi = fibNg(lo);
      const norm = (v) => (v - ngLo) / (ngHi - ngLo);
      plotCurve(g, W, H, (t) => norm(fibNg(lo + (hi - lo) * t)), 'rgba(244,234,217,0.55)');
      const h = fibHorizon();
      const px = (lam) => 34 + (W - 42) * clamp((lam - lo) / (hi - lo), 0, 1);
      const py = (v) => 12 + (H - 34) * (1 - clamp(norm(v), 0, 1));
      // линия горизонта: тот же n_g со ступенькой
      const yh = py(h.ngIn + LABS.fibDn);
      g.strokeStyle = RU; g.setLineDash([3, 3]); g.lineWidth = 1;
      g.beginPath(); g.moveTo(34, yh); g.lineTo(W - 8, yh); g.stroke();
      g.setLineDash([]);
      g.fillStyle = CY;
      for (const [lam, tag] of [[h.lamIn, 'вход'], [h.lamOut, 'выход']]) {
        const x = px(lam);
        g.beginPath(); g.arc(x, yh, 4, 0, TAU); g.fill();
        g.font = '10px ui-sans-serif, Arial, sans-serif';
        g.textAlign = 'center';
        g.fillText(tag, x, yh - 8);
      }
      g.strokeStyle = CY; g.lineWidth = 1.4;
      g.beginPath(); g.moveTo(px(h.lamIn), yh); g.lineTo(px(h.lamOut), yh); g.stroke();
      g.fillStyle = 'rgba(244,234,217,0.5)';
      g.textAlign = 'center'; g.font = '10px ui-sans-serif, Arial, sans-serif';
      g.fillText('λ₀ = 1270 нм', px(FIB.lam0), H - 26);
    },
  },

  /* — двухщелевой опыт — */
  slit: {
    why: [
      'Складываются не вероятности, а амплитуды: P = |A₁ + A₂|² = |A₁|² + |A₂|² + 2Re(A₁*A₂). Последнее слагаемое и есть интерференция. Разность хода до точки x на экране в дальней зоне равна d·x/L, ей отвечает разность фаз 2πdx/λL, и сумма двух равных амплитуд даёт множитель cos²(πdx/λL). Конечная ширина щели a добавляет огибающую sinc². Длина волны берётся из импульса: λ = h/p, p = √(2m_eE). Максимумы стоят через Δx = λL/d.',
      'Дальняя зона (L ≫ d²/λ), скалярная волна, строго одна энергия — реальный пучок размазан по энергиям, и полосы смазываются. Детектор пути описан грубо, как выключатель: на деле видность полос V и различимость пути D связаны как V² + D² ≤ 1, и бывает всё промежуточное. Кулоновское отталкивание электронов и заряд на краях щелей не учтены.',
    ],
    formula: 'λ = h/p = h/√(2m<sub>e</sub>E)   '
      + 'I(x) ∝ sinc²(πax/λL)·cos²(πdx/λL)   шаг полос Δx = λL/d',
    note: 'Электроны летят по одному, но пятна на экране складываются в полосы: каждый идёт сразу через обе щели. '
      + 'Стоит включить детектор пути — и полосы пропадают, остаётся один колокол от одной щели. '
      + 'Дело не в толчке прибора, а в том, что путь стал в принципе различим: различимость и видность полос — две стороны одного.',
    ctl: [
      { k: 'sl', label: 'Энергия', min: 5, max: 400, step: 1,
        get: () => LABS.slitE, set: (v) => { LABS.slitE = v; LABS.slitDots.length = 0; },
        fmt: (v) => v.toFixed(0) + ' эВ' },
      { k: 'sl', label: 'Щели d', min: 60e-9, max: 900e-9, step: 5e-9,
        get: () => LABS.slitGap, set: (v) => { LABS.slitGap = v; LABS.slitDots.length = 0; },
        fmt: (v) => (v * 1e9).toFixed(0) + ' нм' },
      { k: 'tg', label: 'Детектор пути',
        get: () => LABS.slitWhich, set: (v) => { LABS.slitWhich = v; LABS.slitDots.length = 0; } },
      { k: 'bt', label: () => 'Очистить экран', on: () => { LABS.slitDots.length = 0; } },
    ],
    read: () => {
      const p = Math.sqrt(2 * PH.me * LABS.slitE * PH.e);
      return [
        ['импульс p', sci(p) + ' кг·м/с'],
        ['длина волны де Бройля', sci(PH.h / p * 1e12, 3) + ' пм'],
        ['шаг полос на экране', sci(slitSpacing() * 1e6, 3) + ' мкм'],
        ['скорость электрона', sci(p / PH.me / 1000, 3) + ' км/с'],
        ['попало в экран', String(LABS.slitDots.length)],
        ['видность полос', LABS.slitWhich ? '0' : '1'],
      ];
    },
    plot: (g, W, H) => {
      plotFrame(g, W, H, 'x на экране', 'попадания');
      const span = slitSpacing() * 4.5;
      // накопленные попадания — верхние две трети поля
      g.fillStyle = 'rgba(120,220,255,0.75)';
      for (const d of LABS.slitDots) {
        const x = 34 + (W - 42) * (0.5 + d[0] / (2 * span));
        const y = 16 + (H - 90) * d[1];
        if (x > 34 && x < W - 8) g.fillRect(x, y, 1.6, 1.6);
      }
      // теоретический профиль внизу
      g.strokeStyle = CY; g.lineWidth = 1.4; g.beginPath();
      for (let i = 0; i <= 200; i++) {
        const t = i / 200;
        const v = slitProfile((t - 0.5) * 2 * span, LABS.slitWhich);
        const x = 34 + (W - 42) * t;
        const y = (H - 22) - v * (H * 0.32);
        if (i) g.lineTo(x, y); else g.moveTo(x, y);
      }
      g.stroke();
    },
  },

  /* — неравенство Белла — */
  bell: {
    why: [
      'Для синглета ⟨σ_a ⊗ σ_b⟩ = −cos(a−b) — это прямой расчёт по правилу Борна. Теперь возьмём любую теорию, где у каждой пары есть заранее заданный набор ответов A(a,λ) = ±1 и B(b,λ) = ±1. При фиксированном λ выражение A(a)[B(b) − B(b′)] + A(a′)[B(b) + B(b′)] равно ровно ±2, потому что одна из скобок ноль, а другая ±2. Усреднив по λ, получаем |S| ≤ 2. Квантовая механика на углах 0°, 90°, 45°, 135° даёт 2√2 — это максимум, разрешённый уже самой квантовой теорией (граница Цирельсона).',
      'Счётчик тут разыгрывает готовое квантовое предсказание, а не проверяет его: это демонстрация того, как быстро набирается статистика, а не эксперимент. Настоящая проверка обязана закрыть лазейки — эффективности детекторов, локальности (настройки выбираются, когда сигнал уже не успевает), свободы выбора. Идеальные детекторы, никакого шума и потерь. Ошибка оценена как 2/√(N/4) — грубо.',
    ],
    formula: 'E(a,b) = −cos(a−b)   S = |E(a,b) − E(a,b′) + E(a′,b) + E(a′,b′)|   '
      + 'классика: S ≤ 2, кванты: S ≤ 2√2 ≈ 2,828',
    note: 'Источник шлёт в две стороны запутанную пару. Любая теория, где у частиц есть заранее записанные ответы, '
      + 'обязана держаться в пределе S ≤ 2. Квантовая механика на углах 0°, 90°, 45°, 135° даёт 2√2 — '
      + 'и опыт согласен с ней. Счётчик ниже набирает пары по одной: статистика набегает и сходится к теории.',
    ctl: [
      { k: 'sl', label: 'Угол a', min: -180, max: 180, step: 1,
        get: () => LABS.bellA * 180 / Math.PI, set: (v) => { LABS.bellA = v * Math.PI / 180; bellReset(); },
        fmt: (v) => v.toFixed(0) + '°' },
      { k: 'sl', label: 'Угол a′', min: -180, max: 180, step: 1,
        get: () => LABS.bellA2 * 180 / Math.PI, set: (v) => { LABS.bellA2 = v * Math.PI / 180; bellReset(); },
        fmt: (v) => v.toFixed(0) + '°' },
      { k: 'sl', label: 'Угол b', min: -180, max: 180, step: 1,
        get: () => LABS.bellB * 180 / Math.PI, set: (v) => { LABS.bellB = v * Math.PI / 180; bellReset(); },
        fmt: (v) => v.toFixed(0) + '°' },
      { k: 'sl', label: 'Угол b′', min: -180, max: 180, step: 1,
        get: () => LABS.bellB2 * 180 / Math.PI, set: (v) => { LABS.bellB2 = v * Math.PI / 180; bellReset(); },
        fmt: (v) => v.toFixed(0) + '°' },
      { k: 'bt', label: () => LABS.bellRun ? 'Остановить счёт' : 'Набирать пары',
        on: () => { LABS.bellRun = !LABS.bellRun; } },
      { k: 'bt', label: () => 'Лучшие углы',
        on: () => { LABS.bellA = 0; LABS.bellA2 = Math.PI / 2; LABS.bellB = Math.PI / 4; LABS.bellB2 = 3 * Math.PI / 4; bellReset(); } },
    ],
    read: () => {
      const n = LABS.bellN.reduce((a, b) => a + b, 0);
      const meas = bellMeasured();
      const err = n > 0 ? 2 / Math.sqrt(n / 4) : 0;
      return [
        ['S по теории', bellCHSH().toFixed(4)],
        ['предел классической теории', '2'],
        ['предел Цирельсона', (2 * Math.SQRT2).toFixed(4)],
        ['пар набрано', n.toLocaleString('ru-RU')],
        ['S по счётчику', n > 40 ? meas.toFixed(3) + ' ± ' + err.toFixed(3) : '—'],
        ['классика нарушена', bellCHSH() > 2 ? 'да, на ' + ((bellCHSH() - 2) / 2 * 100).toFixed(1) + ' %' : 'нет'],
      ];
    },
    plot: (g, W, H) => {
      plotFrame(g, W, H, 'a − b', 'E');
      // корреляция как функция разности углов
      plotCurve(g, W, H, (t) => (1 - Math.cos(t * TAU)) / 2, 'rgba(244,234,217,0.4)');
      const pts = [[LABS.bellA, LABS.bellB], [LABS.bellA, LABS.bellB2],
                   [LABS.bellA2, LABS.bellB], [LABS.bellA2, LABS.bellB2]];
      const tags = ['ab', 'ab′', 'a′b', 'a′b′'];
      g.font = '10px ui-sans-serif, Arial, sans-serif'; g.textAlign = 'center';
      pts.forEach((p, i) => {
        let dth = ((p[0] - p[1]) % TAU + TAU) % TAU;
        const x = 34 + (W - 42) * (dth / TAU);
        const y = 12 + (H - 34) * (1 - (1 - Math.cos(dth)) / 2);
        g.fillStyle = i === 1 ? RU : CY;
        g.beginPath(); g.arc(x, y, 4, 0, TAU); g.fill();
        g.fillText(tags[i], x, y - 8);
      });
    },
  },

  /* — эффект Казимира — */
  casimir: {
    why: [
      'Между пластинами помещаются только моды с k = πn/d, снаружи — любые. Складываем нулевые энергии ħω/2 в обоих случаях и вычитаем; обе суммы расходятся, но разность конечна — её вытаскивают регуляризацией (например, дзета-функцией: 1 + 2 + 3 + … → ζ(−1) = −1/12). Остаётся энергия на единицу площади −π²ħc/(720d³), а давление — производная по зазору: P = −∂(E/A)/∂d = −π²ħc/(240d⁴). Знак минус — притяжение.',
      'Идеальные проводники, нулевая температура, строго плоские и параллельные пластины. У настоящих металлов конечная проводимость: на зазорах порядка плазменной длины волны (для золота ~136 нм) сила падает на десятки процентов, и формула переходит в казимировско-лифшицевскую. Шероховатость и пятна поверхностного потенциала добавляют своё. При комнатной температуре и зазоре больше микрона включается тепловой вклад, которого тут нет.',
    ],
    formula: 'P = −π²ħc / (240 d⁴)   F = P·A   '
      + 'энергия: E/A = −π²ħc/(720 d³)',
    note: 'Между двумя зеркалами помещаются не все моды вакуума, а снаружи — все. '
      + 'Разница нулевых колебаний даёт настоящее давление, которое сводит пластины. '
      + 'Оно растёт как четвёртая степень зазора: на микроне это мелочь, на десятке нанометров — атмосферы.',
    ctl: [
      { k: 'sl', label: 'Зазор d', min: -8.5, max: -5, step: 0.01, log: true,
        get: () => LABS.casGap, set: (v) => { LABS.casGap = v; },
        fmt: (v) => v < 1e-6 ? (v * 1e9).toFixed(1) + ' нм' : (v * 1e6).toFixed(2) + ' мкм' },
      { k: 'sl', label: 'Площадь A', min: -6, max: -2, step: 0.01, log: true,
        get: () => LABS.casArea, set: (v) => { LABS.casArea = v; },
        fmt: (v) => sci(v * 1e4, 3) + ' см²' },
    ],
    read: () => {
      const P = casimirPressure(LABS.casGap);
      const F = P * LABS.casArea;
      const E = -(Math.PI ** 2 * PH.hbar * PH.c) / (720 * LABS.casGap ** 3) * LABS.casArea;
      return [
        ['давление', sci(P) + ' Па'],
        ['в атмосферах', sci(Math.abs(P) / 101325, 3)],
        ['сила на пластину', sci(F) + ' Н'],
        ['то же весом', sci(Math.abs(F) / 9.80665 * 1e6, 3) + ' мг'],
        ['энергия зазора', sci(E) + ' Дж'],
        ['длина волны отсечки', sci(2 * LABS.casGap * 1e9, 3) + ' нм'],
      ];
    },
    plot: (g, W, H) => {
      plotFrame(g, W, H, 'd: от 5 нм до 10 мкм', 'lg |P|, Па');
      const l0 = Math.log10(5e-9), l1 = Math.log10(1e-5);
      const v0 = Math.log10(Math.abs(casimirPressure(Math.pow(10, l1))));
      const v1 = Math.log10(Math.abs(casimirPressure(Math.pow(10, l0))));
      plotCurve(g, W, H, (t) => {
        const d = Math.pow(10, l0 + (l1 - l0) * t);
        return (Math.log10(Math.abs(casimirPressure(d))) - v0) / (v1 - v0);
      }, CY);
      plotMark(g, W, H, (Math.log10(LABS.casGap) - l0) / (l1 - l0), WH,
        sci(Math.abs(casimirPressure(LABS.casGap)), 3) + ' Па');
    },
  },

  /* — рождение пар по Швингеру — */
  schwinger: {
    why: [
      'Проинтегрировав электронное поле в постоянном внешнем поле, получают эффективное действие Гейзенберга–Эйлера. У него есть мнимая часть, а вероятность того, что вакуум остался вакуумом, равна e^(−2Im W). Ряд по n — это вклады n-кратного туннелирования: пара рождается, когда поле разводит виртуальные заряды на комптоновскую длину быстрее, чем они схлопываются, и экспонента exp(−nπm²c³/(eEħ)) — обычный барьерный множитель. Величина E_c = m²c³/(eħ) — то поле, которое совершает работу mc² на комптоновской длине.',
      'Поле считается строго постоянным и однородным в пространстве и времени — у сфокусированного лазерного импульса это не так, и порог заметно сдвигается. Обратная реакция рождённых пар на поле не учтена, а именно она ограничивает процесс. Поле чисто электрическое: добавление магнитного меняет ответ качественно. Достижимые сегодня поля на три-четыре порядка ниже E_c, так что число «пар в секунду» здесь — экстраполяция.',
    ],
    formula: 'E<sub>c</sub> = m<sub>e</sub><sup>2</sup>c³/(eħ)   '
      + 'Γ = (e²E²/4π³ħ²c) Σ<sub>n</sub> n<sup>−2</sup> exp(−nπE<sub>c</sub>/E)',
    note: 'Вакуум — не пустота, а среда с виртуальными парами. Достаточно сильное поле разводит пару '
      + 'на комптоновскую длину быстрее, чем она успевает схлопнуться, и пара становится настоящей. '
      + 'Порог не резкий, но экспонента жёсткая: вдвое слабее критического — и рождение падает почти на два порядка, вчетверо слабее — на пять.',
    ctl: [
      { k: 'sl', label: 'Поле E', min: 15.5, max: 19, step: 0.01, log: true,
        get: () => LABS.schwField, set: (v) => { LABS.schwField = v; },
        fmt: (v) => sci(v) + ' В/м' },
      { k: 'bt', label: () => 'На критическое', on: () => { LABS.schwField = SCHWINGER_EC; } },
    ],
    read: () => {
      const E = LABS.schwField;
      const R = schwingerRate(E);
      const vol = 1e-18;              // кубический микрон под пластинами
      return [
        ['критическое поле E' + sup('c'), sci(SCHWINGER_EC) + ' В/м'],
        ['доля от критического', (E / SCHWINGER_EC * 100).toFixed(2) + ' %'],
        ['пар в м³ за секунду', sci(R)],
        ['в кубическом микроне', sci(R * vol) + ' с' + sup(-1)],
        ['ждать первой пары', R * vol > 0 ? dur(1 / (R * vol)) : '∞'],
        ['показатель экспоненты', '−' + (Math.PI * SCHWINGER_EC / E).toFixed(2)],
        ['напряжение на микрон', sci(E * 1e-6) + ' В'],
      ];
    },
    plot: (g, W, H) => {
      plotFrame(g, W, H, 'E, В/м (лог)', 'lg Γ');
      const l0 = 16, l1 = 19;
      const lo = Math.log10(Math.max(schwingerRate(Math.pow(10, l0)), 1e-300));
      const hi = Math.log10(schwingerRate(Math.pow(10, l1)));
      plotCurve(g, W, H, (t) => {
        const E = Math.pow(10, l0 + (l1 - l0) * t);
        const v = Math.log10(Math.max(schwingerRate(E), 1e-300));
        return (v - lo) / (hi - lo);
      }, CY);
      plotMark(g, W, H, (Math.log10(SCHWINGER_EC) - l0) / (l1 - l0), RU, 'Eᶜ');
      plotMark(g, W, H, (Math.log10(LABS.schwField) - l0) / (l1 - l0), WH, null);
    },
  },

  /* — туннелирование — */
  tunnel: {
    why: [
      'Внутри барьера решение уравнения Шрёдингера не осциллирует, а затухает: k = √(2m(E−V₀))/ħ становится мнимым, k = iκ. Сшивая ψ и ψ′ на обеих границах, получаем систему на четыре коэффициента; отношение прошедшего потока к падающему и даёт T = [1 + V₀²sh²(κl)/(4E(V₀−E))]^(−1). При κl ≫ 1 гиперболический синус переходит в экспоненту и T ≈ 16E(V₀−E)/V₀² · e^(−2κl) — та самая экспоненциальная зависимость от ширины. Выше барьера sh переходит в sin, и при sin(kl) = 0 барьер становится полностью прозрачным. Картинка ниже эту формулу не использует: там честно решается уравнение Шрёдингера на сетке, шаг за шагом, и доли вероятности считаются интегралом.',
      'Формула для T написана для монохроматической волны, а пакет конечной ширины несёт целую полосу энергий шириной ΔE ≈ ħ²kΔk/m. Через барьер проходят в основном самые быстрые из них, потому что T зависит от энергии экспоненциально, — поэтому измеренная доля всегда выше формулы, а на широком барьере может быть выше в разы. Это не ошибка счёта, а свойство пакета: чем он длиннее, тем уже полоса и тем ближе результат к формуле. Барьер прямоугольный: настоящий сглажен, для него берут ВКБ с интегралом ∫κ(x)dx. Частица нерелятивистская, бесспиновая, одномерная, без потерь энергии в барьере. У краёв сетки стоит мягкая кайма, которая гасит ушедшее, — иначе волна вернулась бы с другой стороны.',
    ],
    formula: 'κ = √(2m(V₀−E))/ħ   '
      + 'T = [1 + V₀² sh²(κl) / (4E(V₀−E))]<sup>−1</sup>   '
      + 'iħ ∂ψ/∂t = −(ħ²/2m)∂²ψ/∂x² + Vψ',
    note: 'Пакет запускается слева и налетает на барьер. Часть его отражается, часть просачивается насквозь — '
      + 'внутри волна не обрывается, а затухает, и с другой стороны остаётся хвост. Это и есть туннелирование; '
      + 'вероятность падает экспоненциально с шириной, и на этом держатся туннельный микроскоп и альфа-распад. '
      + 'То же самое видно на самом стенде: волна бежит по волноводу над столом. Рядом стоит туннельный микроскоп — '
      + 'тот же барьер, только вакуумный: остриё висит над образцом, и ток между ними меняется в разы от смещения на десятую долю нанометра.',
    ctl: [
      { k: 'sl', label: 'Энергия E', min: 0.05, max: 3, step: 0.01,
        get: () => LABS.tunE, set: (v) => { LABS.tunE = v; }, fmt: (v) => v.toFixed(2) + ' эВ' },
      { k: 'sl', label: 'Барьер V₀', min: 0.05, max: 3, step: 0.01,
        get: () => LABS.tunV, set: (v) => { LABS.tunV = v; }, fmt: (v) => v.toFixed(2) + ' эВ' },
      { k: 'sl', label: 'Ширина l', min: 0.05e-9, max: 2.4e-9, step: 0.01e-9,
        get: () => LABS.tunW, set: (v) => { LABS.tunW = v; }, fmt: (v) => (v * 1e9).toFixed(2) + ' нм' },
      { k: 'bt', label: () => WP.run ? 'Стоп' : (WP.launched ? 'Ещё раз' : 'Запустить электрон'),
        on: () => {
          if (WP.run) { WP.run = false; return; }
          if (WP.launched) wpReset();
          WP.run = true; WP.launched = true;
        } },
      { k: 'tg', label: 'Повторять', get: () => WP.loop, set: (v) => { WP.loop = v; if (v) { wpReset(); WP.run = true; WP.launched = true; } } },
      { k: 'sl', label: 'Микроскоп: зазор', min: 0.35, max: 1.1, step: 0.005,
        get: () => STM.gap, set: (v) => { STM.gap = v; }, fmt: (v) => v.toFixed(3) + ' нм' },
      { k: 'sl', label: 'Работа выхода φ', min: 2, max: 6, step: 0.05,
        get: () => STM.phi, set: (v) => { STM.phi = v; }, fmt: (v) => v.toFixed(2) + ' эВ' },
    ],
    read: () => {
      const T = tunnelT(LABS.tunE, LABS.tunV, LABS.tunW);
      const under = LABS.tunE < LABS.tunV;
      const kap = under ? Math.sqrt(2 * PH.me * (LABS.tunV - LABS.tunE) * PH.e) / PH.hbar : 0;
      const k = stmKappa();
      return [
        ['T по формуле', sci(T, 4)],
        ['прошло в опыте', WP.launched ? (WP.right * 100).toFixed(2) + ' %' : '—'],
        ['отразилось', WP.launched ? (WP.left * 100).toFixed(2) + ' %' : '—'],
        ['ещё в барьере', WP.launched ? (WP.inside * 100).toFixed(2) + ' %' : '—'],
        ['прошло времени', WP.launched ? WP.t.toFixed(2) + ' фс' : '0 фс'],
        ['разброс энергии пакета', '±' + wpSpread().toFixed(3) + ' эВ'],
        [under ? 'глубина затухания 1/κ' : 'режим',
          under ? sci(1 / kap * 1e9, 3) + ' нм' : 'над барьером'],
        ['длина волны снаружи',
          sci(PH.h / Math.sqrt(2 * PH.me * LABS.tunE * PH.e) * 1e9, 3) + ' нм'],
        ['ток микроскопа', sci(stmCurrent(STM.gap), 3) + ' нА'],
        ['κ работы выхода', k.toFixed(2) + ' нм' + sup(-1)],
        ['на 0,1 нм ближе ток вырастет в', Math.exp(2 * k * 0.1).toFixed(1) + ' раз'],
      ];
    },
    plot: (g, W, H) => {
      if (!WP.re) wpReset();
      g.clearRect(0, 0, W, H);
      g.fillStyle = 'rgba(6,10,12,0.78)';
      g.fillRect(0, 0, W, H);
      const L = 34, R = W - 8;
      const px = (x) => L + (R - L) * (x - WP.xa) / (WP.xb - WP.xa);
      const split = H * 0.60;              // выше — волна, ниже — профиль энергии
      const h = wpHalf();

      // полоса барьера через всю картинку
      g.fillStyle = 'rgba(150,110,190,0.16)';
      g.fillRect(px(-h), 8, px(h) - px(-h), H - 22);

      // сетка
      g.strokeStyle = 'rgba(244,234,217,0.10)'; g.lineWidth = 1;
      for (let i = -6; i <= 6; i += 2) {
        g.beginPath(); g.moveTo(px(i), 8); g.lineTo(px(i), H - 14); g.stroke();
      }

      // — плотность вероятности и действительная часть
      let mx = 1e-9, mxr = 0;
      for (let i = 0; i < WP.N; i++) {
        const d = wpDens(i);
        if (d > mx) mx = d;
        if (wpX(i) > h && d > mxr) mxr = d;
      }
      // масштаб фиксируем по начальному пакету, чтобы было видно, как он делится
      WP.scale = WP.t === 0 ? mx : (WP.scale || mx);
      const sc = Math.max(WP.scale, mx * 0.35);
      // прошедший хвост обычно в сотню раз ниже — за барьером растягиваем его,
      // иначе туннелирование просто не увидеть
      const gain = mxr > 0 ? clamp(sc * 0.45 / mxr, 1, 400) : 1;
      const scAt = (x) => (x > h ? sc / gain : sc);
      const base = split - 6;
      const yOf = (i) => base - clamp(wpDens(i) / scAt(wpX(i)), 0, 1.05) * (base - 14);
      g.fillStyle = 'rgba(47,214,200,0.28)';
      g.beginPath();
      g.moveTo(px(WP.xa), base);
      for (let i = 0; i < WP.N; i++) g.lineTo(px(wpX(i)), yOf(i));
      g.lineTo(px(WP.xb), base); g.closePath(); g.fill();
      g.strokeStyle = CY; g.lineWidth = 1.4;
      g.beginPath();
      for (let i = 0; i < WP.N; i++) {
        if (i) g.lineTo(px(wpX(i)), yOf(i)); else g.moveTo(px(wpX(i)), yOf(i));
      }
      g.stroke();
      if (gain > 1.5) {
        g.fillStyle = 'rgba(47,214,200,0.75)';
        g.font = '10px ui-sans-serif, Arial, sans-serif'; g.textAlign = 'center';
        g.fillText('масштаб ×' + Math.round(gain), (px(h) + px(WP.xb)) / 2, base + 11);
      }
      // сама волна: осциллирующая действительная часть
      const amp = Math.sqrt(sc) || 1;
      g.strokeStyle = 'rgba(244,234,217,0.42)'; g.lineWidth = 1;
      g.beginPath();
      for (let i = 0; i < WP.N; i++) {
        const y = base - 12 - (WP.re[i] / amp) * (base - 30) * 0.42;
        if (i) g.lineTo(px(wpX(i)), y); else g.moveTo(px(wpX(i)), y);
      }
      g.stroke();

      // — профиль потенциала и уровень энергии
      const top = Math.max(LABS.tunV, LABS.tunE) * 1.35;
      const py = (e) => (H - 16) - (e / top) * (H - 16 - split - 4);
      g.strokeStyle = 'rgba(200,150,240,0.9)'; g.lineWidth = 1.6;
      g.beginPath();
      g.moveTo(L, py(0)); g.lineTo(px(-h), py(0)); g.lineTo(px(-h), py(LABS.tunV));
      g.lineTo(px(h), py(LABS.tunV)); g.lineTo(px(h), py(0)); g.lineTo(R, py(0));
      g.stroke();
      g.strokeStyle = RU; g.setLineDash([4, 3]); g.lineWidth = 1.2;
      g.beginPath(); g.moveTo(L, py(LABS.tunE)); g.lineTo(R, py(LABS.tunE)); g.stroke();
      g.setLineDash([]);

      g.font = '10px ui-sans-serif, Arial, sans-serif';
      g.fillStyle = RU; g.textAlign = 'left';
      g.fillText('E = ' + LABS.tunE.toFixed(2) + ' эВ', L + 4, py(LABS.tunE) - 3);
      g.fillStyle = 'rgba(200,150,240,0.9)'; g.textAlign = 'center';
      g.fillText('V₀ = ' + LABS.tunV.toFixed(2), (px(-h) + px(h)) / 2, py(LABS.tunV) - 4);
      g.fillStyle = 'rgba(244,234,217,0.45)'; g.textAlign = 'right';
      g.fillText('x, нм', R, H - 4);
      g.textAlign = 'left';
      g.fillText('|ψ|²', L + 4, 18);
      if (WP.launched) {
        g.textAlign = 'right';
        g.fillStyle = CY;
        g.fillText('прошло ' + (WP.right * 100).toFixed(1) + ' %', R - 4, 18);
      }
    },
    plot2: (g, W, H) => {
      // — карта тока под остриём: тот же экспоненциальный закон, но по поверхности.
      //   Картинка зависит только от работы выхода, поэтому её кешируем.
      const spanX = 2.6, spanY = spanX * H / W;      // нм
      stmImage(W, H, spanX, spanY);
      g.drawImage(STM.canvas, 0, 0);
      // строчка развёртки
      const sx = Math.floor(STM.scan * W);
      g.fillStyle = 'rgba(255,255,255,0.55)';
      g.fillRect(sx, 0, 1, H);
      g.fillStyle = 'rgba(6,10,12,0.72)';
      g.fillRect(0, H - 15, W, 15);
      g.font = '10px ui-sans-serif, Arial, sans-serif';
      g.fillStyle = 'rgba(244,234,217,0.75)'; g.textAlign = 'left';
      g.fillText('скан 2,6 × ' + spanY.toFixed(1) + ' нм · зазор ' + STM.gap.toFixed(3)
        + ' нм · ток ' + sci(stmCurrent(STM.gap), 2) + ' нА', 6, H - 4);
    },
  },
};

/* ---------------- счётчик Белла ---------------- */

function bellReset() {
  LABS.bellN = [0, 0, 0, 0];
  LABS.bellSum = [0, 0, 0, 0];
}

/** S, собранный из накопленных совпадений. */
function bellMeasured() {
  const e = LABS.bellN.map((n, i) => (n > 0 ? LABS.bellSum[i] / n : 0));
  return Math.abs(e[0] - e[1] + e[2] + e[3]);
}

/** Одна пара: настройки выбираются случайно, исход — по квантовой вероятности. */
function bellShot() {
  const i = (Math.random() * 4) | 0;
  const a = i < 2 ? LABS.bellA : LABS.bellA2;
  const b = i % 2 === 0 ? LABS.bellB : LABS.bellB2;
  const E = bellE(a, b);
  const same = Math.random() < (1 + E) / 2;
  LABS.bellN[i]++;
  LABS.bellSum[i] += same ? 1 : -1;
}

/* ---------------- панель на экране ---------------- */

const LABUI = { built: '', acc: 0 };

function labBind() {
  if (LABUI.root) return;
  LABUI.root = document.getElementById('lab');
  LABUI.title = document.getElementById('lab-title');
  LABUI.formula = document.getElementById('lab-formula');
  LABUI.note = document.getElementById('lab-note');
  LABUI.why = document.getElementById('lab-why');
  LABUI.whyBox = document.getElementById('lab-why-box');
  LABUI.read = document.getElementById('lab-read');
  LABUI.ctl = document.getElementById('lab-ctl');
  LABUI.plot = document.getElementById('lab-plot');
  LABUI.g = LABUI.plot.getContext('2d');
  LABUI.plot2 = document.getElementById('lab-plot2');
  LABUI.g2 = LABUI.plot2.getContext('2d');
  document.getElementById('lab-close').addEventListener('click', () => closeStation());
}

/** Ползунок: обычный или логарифмический — тогда границы заданы степенями десяти. */
function labSlider(c) {
  const wrap = document.createElement('label');
  wrap.className = 'lab-sl';
  const cap = document.createElement('span');
  const val = document.createElement('b');
  cap.textContent = c.label + ' ';
  cap.appendChild(val);
  const inp = document.createElement('input');
  inp.type = 'range';
  inp.min = c.min; inp.max = c.max; inp.step = c.step;
  inp.value = c.log ? Math.log10(c.get()) : c.get();
  const show = () => { val.textContent = c.fmt(c.get()); };
  inp.addEventListener('input', () => {
    const v = parseFloat(inp.value);
    c.set(c.log ? Math.pow(10, v) : v);
    show(); labSync(true);
  });
  show();
  wrap.appendChild(cap); wrap.appendChild(inp);
  wrap.__sync = () => {
    const v = c.log ? Math.log10(c.get()) : c.get();
    if (document.activeElement !== inp) inp.value = v;
    show();
  };
  return wrap;
}

/** Кнопка или переключатель. */
function labButton(c) {
  const b = document.createElement('button');
  b.className = c.k === 'tg' ? 'lab-tg' : 'lab-bt';
  const text = () => (c.k === 'tg' ? c.label : c.label());
  b.textContent = text();
  b.addEventListener('click', () => {
    if (c.k === 'tg') c.set(!c.get()); else c.on();
    b.textContent = text();
    if (c.k === 'tg') b.classList.toggle('on', c.get());
    labSync(true);
  });
  if (c.k === 'tg') b.classList.toggle('on', c.get());
  b.__sync = () => {
    b.textContent = text();
    if (c.k === 'tg') b.classList.toggle('on', c.get());
  };
  return b;
}

/** Пересобрать панель под выбранный стенд. */
function labBuild(id) {
  const st = STATIONS.find((s) => s.id === id);
  const p = PANELS[id];
  labBind();
  LABUI.title.textContent = st.name;
  // формулы разложены по строкам: в одну они склеиваются в кашу
  LABUI.formula.innerHTML = p.formula.replace(/[\s\u2000-\u200a\u00a0]{2,}/g, '<br>');
  LABUI.note.textContent = p.note;
  // вывод и допущения — под раскрывашкой: кому надо, тот развернёт
  LABUI.why.innerHTML = '';
  for (const [head, text] of [['Откуда формула', p.why[0]], ['Где она врёт', p.why[1]]]) {
    const h = document.createElement('b');
    h.textContent = head;
    const q = document.createElement('p');
    q.textContent = text;
    LABUI.why.appendChild(h);
    LABUI.why.appendChild(q);
  }
  LABUI.whyBox.open = false;
  LABUI.ctl.innerHTML = '';
  LABUI.rows = [];
  for (const c of p.ctl) {
    const el = c.k === 'sl' ? labSlider(c) : labButton(c);
    LABUI.ctl.appendChild(el);
    LABUI.rows.push(el);
  }
  LABUI.built = id;
  LABUI.readHtml = '';
  labSync(true);
}

/** Обновить числа, график и подписи органов управления. */
function labSync(force) {
  if (!LABS.open || !LABUI.root) return;
  const p = PANELS[LABS.open];
  let html = '';
  for (const [k, v] of p.read()) html += '<i>' + k + '</i><b>' + v + '</b>';
  // перекладываем разметку, только если числа и правда изменились
  if (html !== LABUI.readHtml) { LABUI.readHtml = html; LABUI.read.innerHTML = html; }
  p.plot(LABUI.g, LABUI.plot.width, LABUI.plot.height);
  LABUI.plot2.style.display = p.plot2 ? 'block' : 'none';
  if (p.plot2) p.plot2(LABUI.g2, LABUI.plot2.width, LABUI.plot2.height);
  if (force) for (const el of LABUI.rows) el.__sync();
}

function openStation(id) {
  if (!PANELS[id]) return false;
  labBind();
  LABS.open = id;
  if (LABUI.built !== id) labBuild(id); else labSync(true);
  LABUI.root.classList.add('show');
  document.getElementById('app').classList.add('lab-open');
  return true;
}

function closeStation() {
  if (!LABS.open) return false;
  LABS.open = null;
  LABUI.root.classList.remove('show');
  document.getElementById('app').classList.remove('lab-open');
  return true;
}

/** Ближайший стенд, если мы у него стоим. */
function nearStation() {
  if (game.world !== 'earth' || game.mode !== 'walk') return null;
  if (game.rocket.inside || game.tent.inside) return null;
  for (const s of STATIONS) {
    if (Math.hypot(cam.x - s.sx, cam.z - s.sz) < 2.1) return s;
  }
  return null;
}

/** Нажали E или ткнули в экран: открыть стенд или закрыть открытый. */
function labUse() {
  if (LABS.open) {
    const s = nearStation();
    if (s && s.id !== LABS.open) return openStation(s.id);
    return closeStation();
  }
  const s = nearStation();
  return s ? openStation(s.id) : false;
}

/* ---------------- ход опытов ---------------- */

function updateLab(dt) {
  LABS.t += dt;
  // отошли от стенда — панель закрывается сама
  if (LABS.open) {
    const s = STATIONS.find((q) => q.id === LABS.open);
    if (game.world !== 'earth' || Math.hypot(cam.x - s.sx, cam.z - s.sz) > 4.5) closeStation();
  }

  if (LABS.evapRun) {
    LABS.evapU += dt / LABS.evapSpan;
    if (LABS.evapU >= 1) { LABS.evapU = 0.999999; LABS.evapRun = false; }
  }

  // связь стенда с дырой за стеной: радиус горизонта идёт от массы в опыте
  if (LABS.evapLive) {
    const M = evapMass();
    if (LABS.evapU >= 0.999999) {
      if (!LABS.evapGone) {
        LABS.evapGone = true;
        bhSetMass(0);
        // последние килограммы уходят вспышкой — это и есть конец испарения
        BLAST.flash = 0.95; BLAST.flashHold = 0.30;
      }
    } else if (!bhSetMass(M)) {
      LABS.evapLive = false;
      bhRestore();
      LABS.evapNote = 'оборвана: горизонт накрыл бы полигон';
    }
  }

  if (LABS.bellRun) {
    LABS.bellAcc += dt * 900;
    const n = Math.min(4000, Math.floor(LABS.bellAcc));
    LABS.bellAcc -= n;
    for (let i = 0; i < n; i++) bellShot();
  }

  if (LABS.open === 'slit') {
    LABS.slitAcc += dt * LABS.slitRate;
    const n = Math.min(60, Math.floor(LABS.slitAcc));
    LABS.slitAcc -= n;
    const span = slitSpacing() * 4.5;
    for (let i = 0; i < n; i++) {
      // выборка с отбраковкой по самому профилю
      for (let k = 0; k < 40; k++) {
        const x = (Math.random() - 0.5) * 2 * span;
        if (Math.random() < slitProfile(x, LABS.slitWhich)) {
          LABS.slitDots.push([x, Math.random()]);
          break;
        }
      }
    }
    while (LABS.slitDots.length > 2600) LABS.slitDots.shift();
  }

  // туннельный стенд: пакет считается всегда, когда стенд открыт или мы рядом
  if (LABS.open === 'tunnel' || tunnelNear()) {
    if (!WP.re || WP.key !== wpKey()) { wpReset(); if (WP.loop) { WP.run = true; WP.launched = true; } }
    if (WP.run) {
      // держим постоянный ход опыта: около четырёх фемтосекунд на секунду
      const steps = clamp(Math.round(4.0 * dt / WP.dt), 1, 1400);
      wpStep(steps);
      if (WP.t > WP.tEnd) {
        if (WP.loop) { wpReset(); WP.run = true; WP.launched = true; } else WP.run = false;
      }
    }
    STM.scan = (STM.scan + dt * 0.22) % 1;
  }

  if (LABS.fibOn) {
    // импульсы идут пачкой: за секунду через горизонт проходит своя доля пробы
    LABS.fibN += dt * 3.0e8;
    const spent = LABS.fibN * fibQuantum();
    if (spent > FIB.ePulse * 0.5) LABS.fibOn = false;   // импульс выдохся
  }

  // панель освежается десять раз в секунду, чаще не нужно
  if (LABS.open) {
    LABUI.acc += dt;
    if (LABUI.acc > 0.14) { LABUI.acc = 0; labSync(false); }
  }
}

/* ---------------- волна на самом стенде ---------------- */

/* Над волноводом туннельного стенда светится цепочка точек: их высота и
   яркость — та же |ψ|², что и на панели. Считаем только вблизи. */
const TUNPTS = { n: 72, pos: null, col: null, buf: null, cbuf: null, ready: false };

/** Стоим ли мы достаточно близко к туннельному стенду, чтобы волну считать. */
function tunnelNear() {
  if (game.world !== 'earth') return false;
  const st = STATIONS.find((q) => q.id === 'tunnel');
  return Math.hypot(cam.x - st.x, cam.z - st.z) < 16;
}

function tunPointsInit() {
  TUNPTS.pos = new Float32Array(TUNPTS.n * 3);
  TUNPTS.col = new Float32Array(TUNPTS.n * 4);
  TUNPTS.buf = gl.createBuffer();
  TUNPTS.cbuf = gl.createBuffer();
  TUNPTS.ready = true;
}

function tunPointsUpdate() {
  const st = STATIONS.find((q) => q.id === 'tunnel');
  const co = Math.cos(-st.yaw), si = Math.sin(-st.yaw);
  const h = wpHalf();
  let mx = 1e-9;
  for (let i = 0; i < WP.N; i++) mx = Math.max(mx, wpDens(i));
  const sc = Math.max(WP.scale || mx, mx * 0.35);
  for (let p = 0; p < TUNPTS.n; p++) {
    const u = p / (TUNPTS.n - 1);
    const gi = Math.round(u * (WP.N - 1));
    const d = clamp(wpDens(gi) / sc, 0, 1.6);
    const lx = -0.15 + (u - 0.5) * 1.72;             // вдоль волновода
    const ly = 1.05 + d * 0.30;
    const j = p * 3;
    TUNPTS.pos[j] = st.x + lx * co;
    TUNPTS.pos[j + 1] = LAB.y + ly;
    TUNPTS.pos[j + 2] = st.z + lx * si;
    const inside = Math.abs(wpX(gi)) <= h;
    const q = p * 4;
    TUNPTS.col[q] = inside ? 0.72 : 0.30;
    TUNPTS.col[q + 1] = inside ? 0.44 : 0.88;
    TUNPTS.col[q + 2] = inside ? 0.95 : 0.86;
    TUNPTS.col[q + 3] = clamp(0.12 + d * 1.1, 0, 1);
  }
  gl.bindBuffer(gl.ARRAY_BUFFER, TUNPTS.buf);
  gl.bufferData(gl.ARRAY_BUFFER, TUNPTS.pos, gl.DYNAMIC_DRAW);
  gl.bindBuffer(gl.ARRAY_BUFFER, TUNPTS.cbuf);
  gl.bufferData(gl.ARRAY_BUFFER, TUNPTS.col, gl.DYNAMIC_DRAW);
}

/** Точки волны. Вызывается там же, где пары у горизонта. */
function drawTunnelWave() {
  if (!WP.re || !tunnelNear()) return;
  if (!TUNPTS.ready) tunPointsInit();
  tunPointsUpdate();
  gl.useProgram(pointProg.prog);
  gl.uniformMatrix4fv(pointProg.u.uVP, false, vp);
  gl.uniform3fv(pointProg.u.uCam, [cam.x, cam.y, cam.z]);
  gl.uniform1f(pointProg.u.uScale, 15 * (canvas.height / 700));
  attrib(pointProg.a.aPos, TUNPTS.buf, 3);
  attrib(pointProg.a.aColor, TUNPTS.cbuf, 4);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
  gl.depthMask(false);
  gl.drawArrays(gl.POINTS, 0, TUNPTS.n);
  gl.depthMask(true);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
}

/* ---------------- отрисовка ---------------- */

/* Телескоп на стенде испарения смотрит не в потолок, а на ту самую дыру:
   труба доворачивается каждый кадр по направлению из своей опоры. */
const SCOPE = { lx: 0, ly: 1.36, lz: 0 };

/** Матрица трубы: локальная ось +z наводится на точку в мире. */
function scopeMatrix(out) {
  const st = STATIONS.find((q) => q.id === 'evap');
  const co = Math.cos(-st.yaw), si = Math.sin(-st.yaw);
  // опора телескопа в мировых координатах
  const px = st.x + SCOPE.lx * co - SCOPE.lz * si;
  const pz = st.z + SCOPE.lx * si + SCOPE.lz * co;
  const py = LAB.y + SCOPE.ly;
  let dx = BH.pos[0] - px, dy = BH.pos[1] - py, dz = BH.pos[2] - pz;
  const l = Math.hypot(dx, dy, dz) || 1;
  dx /= l; dy /= l; dz /= l;
  // R = Ry·Rx: третий столбец матрицы должен лечь на направление
  return m4compose(out, px, py, pz, Math.atan2(dx, dz), Math.asin(clamp(-dy, -1, 1)), 0, 1);
}

let LABMESH = null;
const labM = m4();

/** Табличка стенда: тёмная плашка с названием, читается издали. */
function makeLabSign(text, sub) {
  const W = 512, H = 128;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const g = c.getContext('2d');
  g.clearRect(0, 0, W, H);
  g.fillStyle = 'rgba(10,16,18,0.88)';
  g.fillRect(6, 10, W - 12, H - 20);
  g.strokeStyle = 'rgba(47,214,200,0.55)';
  g.lineWidth = 2;
  g.strokeRect(6, 10, W - 12, H - 20);
  g.textAlign = 'center';
  g.textBaseline = 'middle';
  g.fillStyle = 'rgba(230,246,244,0.96)';
  g.font = '600 44px ui-sans-serif, "Helvetica Neue", Arial, sans-serif';
  if ('letterSpacing' in g) g.letterSpacing = '2px';
  g.fillText(text, W / 2, sub ? H / 2 - 12 : H / 2);
  if (sub) {
    g.font = '500 22px ui-sans-serif, Arial, sans-serif';
    g.fillStyle = 'rgba(47,214,200,0.85)';
    g.fillText(sub, W / 2, H / 2 + 26);
  }
  return c;
}

/** Прямоугольная табличка-билборд: та же раскладка атрибутов, что у подписей фигур. */
function labQuad(cx, cy, cz, w, h) {
  const center = [], corner = [], uv = [], phase = [];
  for (const [dx, dy, u, v] of [[-w, -h, 0, 0], [w, -h, 1, 0], [w, h, 1, 1], [-w, h, 0, 1]]) {
    center.push(cx, cy, cz); corner.push(dx, dy); uv.push(u, v); phase.push(0);
  }
  return {
    center: buffer(new Float32Array(center)),
    corner: buffer(new Float32Array(corner)),
    uv: buffer(new Float32Array(uv)),
    phase: buffer(new Float32Array(phase)),
    idx: buffer(new Uint16Array([0, 1, 2, 0, 2, 3]), gl.ELEMENT_ARRAY_BUFFER),
    count: 6,
  };
}

function labAssets() {
  LABMESH = { shell: buildLab(), rigs: buildRigs(), signs: [] };
  LABMESH.signs.push({
    tex: texture(makeLabSign('КВАНТОВЫЙ ЗАЛ', 'наблюдение эффектов КМ и КТП')),
    quad: labQuad(LAB.x, LAB.y + 3.95, LAB.z - LAB.d - 0.16, 2.36, 0.59),
    x: LAB.x, z: LAB.z - LAB.d, near: 3.0,
  });
  for (const s of STATIONS) {
    LABMESH.signs.push({
      tex: texture(makeLabSign(s.name)),
      quad: labQuad(s.x, LAB.y + 2.42, s.z, 1.05, 0.2625),
      x: s.x, z: s.z, near: 2.0,
    });
  }
  return LABMESH;
}

function labMeshDraw(mesh) {
  attrib(solidProg.a.aPos, mesh.pos, 3);
  attrib(solidProg.a.aNormal, mesh.nrm, 3);
  attrib(solidProg.a.aColor, mesh.col, 3);
  gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, mesh.idx);
  gl.drawElements(gl.TRIANGLES, mesh.count, gl.UNSIGNED_SHORT, 0);
}

/** Корпус и установки. Вызывается там, где уже настроен solidProg. */
function drawLab() {
  if (!LABMESH) return;
  // в зале горит свой свет: без подсветки бетонная коробка читается погребом
  const lamp = 1.22 + 0.42 * (1 - clamp(LIGHT[1] / 0.8, 0, 1));
  gl.uniform3f(solidProg.u.uTint, lamp, lamp * 0.995, lamp * 0.97);
  gl.uniformMatrix4fv(solidProg.u.uModel, false, m4identity(labM));
  labMeshDraw(LABMESH.shell);
  for (const s of STATIONS) {
    const rig = LABMESH.rigs[s.id];
    if (!rig) continue;
    m4compose(labM, s.x, LAB.y, s.z, -s.yaw, 0, 0, 1);
    gl.uniformMatrix4fv(solidProg.u.uModel, false, labM);
    labMeshDraw(rig);
  }
  gl.uniformMatrix4fv(solidProg.u.uModel, false, scopeMatrix(labM));
  labMeshDraw(LABMESH.rigs.evapScope);
  gl.uniform3f(solidProg.u.uTint, 1, 1, 1);
  gl.uniformMatrix4fv(solidProg.u.uModel, false, m4identity(labM));
}

/** Таблички. Вызывается в блоке спрайтов. */
function drawLabSigns() {
  if (!LABMESH) return;
  if (Math.hypot(cam.x - LAB.x, cam.z - LAB.z) > 130) return;
  for (const s of LABMESH.signs) {
    const d = Math.hypot(cam.x - s.x, cam.z - s.z);
    // у самого носа табличка закрыла бы половину экрана — гасим
    const fade = clamp((d - s.near) / 1.3, 0, 1) * clamp((120 - d) / 30, 0, 1);
    if (fade < 0.02) continue;
    gl.uniform1f(spriteProg.u.uFade, fade);
    gl.bindTexture(gl.TEXTURE_2D, s.tex);
    attrib(spriteProg.a.aCenter, s.quad.center, 3);
    attrib(spriteProg.a.aCorner, s.quad.corner, 2);
    attrib(spriteProg.a.aUv, s.quad.uv, 2);
    attrib(spriteProg.a.aPhase, s.quad.phase, 1);
    gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, s.quad.idx);
    gl.drawElements(gl.TRIANGLES, s.quad.count, gl.UNSIGNED_SHORT, 0);
  }
}
