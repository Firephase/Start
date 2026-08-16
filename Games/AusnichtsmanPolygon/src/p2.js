/* ============================================================
   Полигон Мёбиуса — три ленты над пустыней Невада.
   Чистый WebGL 1, без библиотек: вся геометрия, небо, песок,
   кусты и звук ветра считаются процедурно.
   ============================================================ */

const TAU = Math.PI * 2;
const clamp = (x, a, b) => (x < a ? a : x > b ? b : x);
const lerp = (a, b, t) => a + (b - a) * t;
const smoothstep = (e0, e1, x) => {
  const t = clamp((x - e0) / (e1 - e0), 0, 1);
  return t * t * (3 - 2 * t);
};
/** Приближение к цели, не зависящее от частоты кадров. */
const damp = (a, b, rate, dt) => lerp(a, b, 1 - Math.exp(-rate * dt));

/** Детерминированный генератор — мир одинаков при каждом запуске. */
function rng(seed) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}

/* ---------------- матрицы 4×4 (column-major) ---------------- */

const m4 = () => new Float32Array(16);

function m4identity(o) {
  o.fill(0); o[0] = o[5] = o[10] = o[15] = 1; return o;
}

function m4mul(o, a, b) {
  for (let c = 0; c < 4; c++) {
    const b0 = b[c * 4], b1 = b[c * 4 + 1], b2 = b[c * 4 + 2], b3 = b[c * 4 + 3];
    o[c * 4]     = a[0] * b0 + a[4] * b1 + a[8]  * b2 + a[12] * b3;
    o[c * 4 + 1] = a[1] * b0 + a[5] * b1 + a[9]  * b2 + a[13] * b3;
    o[c * 4 + 2] = a[2] * b0 + a[6] * b1 + a[10] * b2 + a[14] * b3;
    o[c * 4 + 3] = a[3] * b0 + a[7] * b1 + a[11] * b2 + a[15] * b3;
  }
  return o;
}

function m4perspective(o, fovy, aspect, near, far) {
  const f = 1 / Math.tan(fovy / 2);
  o.fill(0);
  o[0] = f / aspect; o[5] = f; o[11] = -1;
  o[10] = (far + near) / (near - far);
  o[14] = (2 * far * near) / (near - far);
  return o;
}

function m4lookAt(o, eye, at, up) {
  let zx = eye[0] - at[0], zy = eye[1] - at[1], zz = eye[2] - at[2];
  let l = Math.hypot(zx, zy, zz) || 1; zx /= l; zy /= l; zz /= l;
  let xx = up[1] * zz - up[2] * zy, xy = up[2] * zx - up[0] * zz, xz = up[0] * zy - up[1] * zx;
  l = Math.hypot(xx, xy, xz) || 1; xx /= l; xy /= l; xz /= l;
  const yx = zy * xz - zz * xy, yy = zz * xx - zx * xz, yz = zx * xy - zy * xx;
  o[0] = xx; o[1] = yx; o[2] = zx; o[3] = 0;
  o[4] = xy; o[5] = yy; o[6] = zy; o[7] = 0;
  o[8] = xz; o[9] = yz; o[10] = zz; o[11] = 0;
  o[12] = -(xx * eye[0] + xy * eye[1] + xz * eye[2]);
  o[13] = -(yx * eye[0] + yy * eye[1] + yz * eye[2]);
  o[14] = -(zx * eye[0] + zy * eye[1] + zz * eye[2]);
  o[15] = 1;
  return o;
}

function m4invert(o, m) {
  const a00=m[0],a01=m[1],a02=m[2],a03=m[3], a10=m[4],a11=m[5],a12=m[6],a13=m[7],
        a20=m[8],a21=m[9],a22=m[10],a23=m[11], a30=m[12],a31=m[13],a32=m[14],a33=m[15];
  const b00=a00*a11-a01*a10, b01=a00*a12-a02*a10, b02=a00*a13-a03*a10,
        b03=a01*a12-a02*a11, b04=a01*a13-a03*a11, b05=a02*a13-a03*a12,
        b06=a20*a31-a21*a30, b07=a20*a32-a22*a30, b08=a20*a33-a23*a30,
        b09=a21*a32-a22*a31, b10=a21*a33-a23*a31, b11=a22*a33-a23*a32;
  let det = b00*b11 - b01*b10 + b02*b09 + b03*b08 - b04*b07 + b05*b06;
  if (!det) return m4identity(o);
  det = 1 / det;
  o[0]=(a11*b11-a12*b10+a13*b09)*det;  o[1]=(a02*b10-a01*b11-a03*b09)*det;
  o[2]=(a31*b05-a32*b04+a33*b03)*det;  o[3]=(a22*b04-a21*b05-a23*b03)*det;
  o[4]=(a12*b08-a10*b11-a13*b07)*det;  o[5]=(a00*b11-a02*b08+a03*b07)*det;
  o[6]=(a32*b02-a30*b05-a33*b01)*det;  o[7]=(a20*b05-a22*b02+a23*b01)*det;
  o[8]=(a10*b10-a11*b08+a13*b06)*det;  o[9]=(a01*b08-a00*b10-a03*b06)*det;
  o[10]=(a30*b04-a31*b02+a33*b00)*det; o[11]=(a21*b02-a20*b04-a23*b00)*det;
  o[12]=(a11*b07-a10*b09-a12*b06)*det; o[13]=(a00*b09-a01*b07+a02*b06)*det;
  o[14]=(a31*b01-a30*b03-a32*b00)*det; o[15]=(a20*b03-a21*b01+a22*b00)*det;
  return o;
}

/** Модельная матрица: перенос · Ry · Rx · Rz · равномерный масштаб. */
function m4compose(o, px, py, pz, ry, rx, rz, s) {
  const cy = Math.cos(ry), sy = Math.sin(ry);
  const cx = Math.cos(rx), sx = Math.sin(rx);
  const cz = Math.cos(rz), sz = Math.sin(rz);
  // R = Ry * Rx * Rz
  const r00 = cy * cz + sy * sx * sz, r01 = -cy * sz + sy * sx * cz, r02 = sy * cx;
  const r10 = cx * sz,                r11 = cx * cz,                 r12 = -sx;
  const r20 = -sy * cz + cy * sx * sz, r21 = sy * sz + cy * sx * cz, r22 = cy * cx;
  o[0] = r00 * s; o[1] = r10 * s; o[2] = r20 * s; o[3] = 0;
  o[4] = r01 * s; o[5] = r11 * s; o[6] = r21 * s; o[7] = 0;
  o[8] = r02 * s; o[9] = r12 * s; o[10] = r22 * s; o[11] = 0;
  o[12] = px; o[13] = py; o[14] = pz; o[15] = 1;
  return o;
}

/* ---------------- WebGL ---------------- */

const canvas = document.getElementById('gl');
const glOpts = { antialias: true, alpha: false, depth: true, powerPreference: 'high-performance' };
const gl = canvas.getContext('webgl', glOpts) || canvas.getContext('experimental-webgl', glOpts);

if (!gl) {
  document.getElementById('fail').classList.add('show');
  document.getElementById('cover').classList.add('gone');
  throw new Error('no webgl');
}

const PRECISION = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
`;

function compile(type, src) {
  const s = gl.createShader(type);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(s) + '\n' + src);
  }
  return s;
}

function program(vsSrc, fsSrc) {
  const p = gl.createProgram();
  gl.attachShader(p, compile(gl.VERTEX_SHADER, vsSrc));
  gl.attachShader(p, compile(gl.FRAGMENT_SHADER, fsSrc));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p));

  const wrap = { prog: p, u: {}, a: {} };
  const nu = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < nu; i++) {
    const info = gl.getActiveUniform(p, i);
    wrap.u[info.name.replace('[0]', '')] = gl.getUniformLocation(p, info.name);
  }
  const na = gl.getProgramParameter(p, gl.ACTIVE_ATTRIBUTES);
  for (let i = 0; i < na; i++) {
    const info = gl.getActiveAttrib(p, i);
    wrap.a[info.name] = gl.getAttribLocation(p, info.name);
  }
  return wrap;
}

function buffer(data, target = gl.ARRAY_BUFFER) {
  const b = gl.createBuffer();
  gl.bindBuffer(target, b);
  gl.bufferData(target, data, gl.STATIC_DRAW);
  return b;
}

function texture(source, { mips = true, wrap = gl.CLAMP_TO_EDGE, wrapS = null, wrapT = null } = {}) {
  const t = gl.createTexture();
  gl.bindTexture(gl.TEXTURE_2D, t);
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, true);
  gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, source);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, wrapS || wrap);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, wrapT || wrap);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  if (mips) {
    gl.generateMipmap(gl.TEXTURE_2D);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
  } else {
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  }
  gl.pixelStorei(gl.UNPACK_FLIP_Y_WEBGL, false);
  return t;
}

/** Привязка атрибута из отдельного буфера. */
function attrib(loc, buf, size, stride = 0, offset = 0) {
  if (loc === undefined || loc < 0) return;
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.enableVertexAttribArray(loc);
  gl.vertexAttribPointer(loc, size, gl.FLOAT, false, stride, offset);
}

/**
 * Матрица поворота, переводящая единичный вектор a в единичный b
 * (формула Родрига). Нужна, чтобы «домашняя» точка планеты всегда
 * оказывалась ровно под кораблём.
 */
function m4align(o, a, b) {
  const d = a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
  let ax = a[1] * b[2] - a[2] * b[1], ay = a[2] * b[0] - a[0] * b[2], az = a[0] * b[1] - a[1] * b[0];
  const l = Math.hypot(ax, ay, az);
  if (l < 1e-7) {                    // совпали или противоположны
    m4identity(o);
    if (d < 0) { o[0] = -1; o[5] = -1; }
    return o;
  }
  ax /= l; ay /= l; az /= l;
  const c = clamp(d, -1, 1), s2 = l, t = 1 - c;
  o[0] = t * ax * ax + c;      o[1] = t * ax * ay + s2 * az; o[2] = t * ax * az - s2 * ay; o[3] = 0;
  o[4] = t * ax * ay - s2 * az; o[5] = t * ay * ay + c;      o[6] = t * ay * az + s2 * ax; o[7] = 0;
  o[8] = t * ax * az + s2 * ay; o[9] = t * ay * az - s2 * ax; o[10] = t * az * az + c;     o[11] = 0;
  o[12] = 0; o[13] = 0; o[14] = 0; o[15] = 1;
  return o;
}

/* Шум для карт планет и мелких деталей поверхности. */
const PLANET_NOISE = `
float hash13(vec3 p) {
  p = fract(p * 0.3183099 + vec3(0.71, 0.113, 0.419));
  p *= 17.0;
  return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}
float vnoise(vec3 x) {
  vec3 i = floor(x), f = fract(x);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(mix(hash13(i + vec3(0.0, 0.0, 0.0)), hash13(i + vec3(1.0, 0.0, 0.0)), f.x),
                 mix(hash13(i + vec3(0.0, 1.0, 0.0)), hash13(i + vec3(1.0, 1.0, 0.0)), f.x), f.y),
             mix(mix(hash13(i + vec3(0.0, 0.0, 1.0)), hash13(i + vec3(1.0, 0.0, 1.0)), f.x),
                 mix(hash13(i + vec3(0.0, 1.0, 1.0)), hash13(i + vec3(1.0, 1.0, 1.0)), f.x), f.y), f.z);
}
float fbm3(vec3 p) {
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 3; i++) { v += vnoise(p) * a; a *= 0.5; p *= 2.03; }
  return v * 1.1428;
}
float fbm6(vec3 p) {
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 6; i++) { v += vnoise(p) * a; a *= 0.5; p *= 2.03; }
  return v * 1.0079;
}
/* хребтовый шум: гребни вместо холмов — из него горные цепи и русла рек */
float ridged(vec3 p) {
  float v = 0.0, a = 0.5;
  for (int i = 0; i < 5; i++) {
    v += (1.0 - abs(vnoise(p) * 2.0 - 1.0)) * a;
    a *= 0.5; p *= 2.11;
  }
  return v * 1.0158;
}
`;

/* ---------------- палитра сцены ---------------- */

/* Небо живое: SUN, HAZE, LIGHT и AMB пересчитываются каждый кадр
   в updateSky() — сутки укладываются в пять минут. */
const SUN = [-0.42, 0.38, -0.82];     // направление на квазар
const HAZE = [0.855, 0.783, 0.662];   // дымка у горизонта
const LIGHT = [1.05, 0.96, 0.84];     // цвет и сила прямого света
const AMB = [1, 1, 1];                // множитель рассеянного света
const FOG_K = 0.0062;
const ACCENT = [0.184, 0.839, 0.784]; // разметочная линия

const DAY_LENGTH = 300;               // секунд на полные сутки
let dayPhase = 0.30;                  // 0 — восход, 0.25 — полдень, 0.5 — закат
let nightAmount = 0;                  // 0 день, 1 ночь

/** Смешение цветов по трём опорным точкам: ночь → закат → день. */
function skyMix(out, night, dusk, day, elev) {
  const dawn = smoothstep(-0.16, 0.02, elev);   // ночь → закат
  const noon = smoothstep(0.02, 0.30, elev);    // закат → день
  for (let i = 0; i < 3; i++) {
    out[i] = lerp(lerp(night[i], dusk[i], dawn), day[i], noon);
  }
}

const EAST = [0.88, 0, -0.47];

function updateSky(worldTime) {
  dayPhase = ((worldTime / DAY_LENGTH) + 0.30) % 1;
  const th = dayPhase * TAU;
  const elev = Math.sin(th);
  const horiz = Math.cos(th);
  const x = EAST[0] * horiz, y = elev * 0.95, z = EAST[2] * horiz;
  const l = Math.hypot(x, y, z) || 1;
  SUN[0] = x / l; SUN[1] = y / l; SUN[2] = z / l;

  nightAmount = 1 - smoothstep(-0.13, 0.05, elev);

  skyMix(HAZE, [0.055, 0.062, 0.105], [0.86, 0.50, 0.33], [0.855, 0.783, 0.662], elev);
  skyMix(LIGHT, [0.10, 0.13, 0.24], [1.15, 0.62, 0.34], [1.05, 0.96, 0.84], elev);
  skyMix(AMB, [0.21, 0.25, 0.38], [0.62, 0.52, 0.52], [1, 1, 1], elev);
  return elev;
}
