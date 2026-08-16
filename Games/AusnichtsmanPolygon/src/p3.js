/* ============================================================
   Шейдеры
   ============================================================ */

/* ---- небо: горизонт, солнце и силуэты хребтов из синусов ---- */

const skyProg = program(`
attribute vec2 aPos;
uniform mat4 uInvVP;
uniform vec3 uCam;
varying vec3 vDir;
void main() {
  vec4 far = uInvVP * vec4(aPos, 1.0, 1.0);
  vDir = far.xyz / far.w - uCam;
  gl_Position = vec4(aPos, 1.0, 1.0);   // ровно дальняя плоскость: LEQUAL отсечёт закрытое
}`, PRECISION + `
varying vec3 vDir;
uniform vec3 uSun;
uniform vec3 uHaze;
uniform float uNight;
uniform float uSpace;
uniform float uZoom;
uniform float uTime;
uniform sampler2D uMilky;

float hash13(vec3 p) {
  p = fract(p * 0.1031);
  p += dot(p, p.yzx + 33.33);
  return fract((p.x + p.y) * p.z);
}

/** Поле звёзд: в редких ячейках сетки направлений зажигается точка. */
float stars(vec3 d, float density, float thr, float sharp) {
  vec3 p = d * density;
  vec3 c = floor(p), f = fract(p) - 0.5;
  float h = hash13(c);
  float on = step(thr, h);
  float jx = hash13(c + 11.0) - 0.5, jy = hash13(c + 27.0) - 0.5, jz = hash13(c + 41.0) - 0.5;
  float dist = length(f - vec3(jx, jy, jz) * 0.7);
  float mag = (h - thr) / max(1e-4, 1.0 - thr);
  float tw = 0.75 + 0.25 * sin(uTime * 2.1 + h * 40.0);   // мерцание
  return on * pow(max(0.0, 1.0 - dist * sharp), 5.0) * mag * tw;
}

float ridge(float a, float seed) {
  return 0.50 * sin(a * 2.7 + seed)
       + 0.28 * sin(a * 5.9 + seed * 2.3)
       + 0.15 * sin(a * 11.7 + seed * 4.1)
       + 0.07 * sin(a * 23.1 + seed * 7.7);
}

void main() {
  vec3 d = normalize(vDir);
  float h = d.y;

  vec3 zenithDay = vec3(0.204, 0.404, 0.706);
  vec3 zenithNight = vec3(0.017, 0.022, 0.055);
  vec3 zenith = mix(zenithDay, zenithNight, max(uNight, uSpace));
  vec3 col = mix(uHaze, zenith, pow(clamp(h, 0.0, 1.0), 0.52));
  col = mix(col, uHaze, exp(-max(h, 0.0) * 14.0) * 0.85 * (1.0 - uSpace));
  col *= 1.0 - 0.92 * uSpace;                       // воздух кончился — остаётся чернота

  // ---- ночное небо: запечённый Млечный Путь плюс живые звёзды ----
  float starLit = max(uNight, uSpace);
  if (starLit > 0.01) {
    vec2 muv = vec2(atan(d.z, d.x) * 0.1591549 + 0.5, asin(clamp(d.y, -1.0, 1.0)) * 0.3183099 + 0.5);
    vec3 mw = texture2D(uMilky, muv).rgb;
    float fade = starLit * mix(smoothstep(-0.03, 0.09, h), 1.0, uSpace);
    col += mw * fade;

    float belt = max(mw.r, max(mw.g, mw.b));               // яркость полосы как плотность звёзд
    float sk = stars(d, 58.0, 0.9760, 2.4) * 1.7
             + stars(d, 118.0, 0.9840, 3.2) * 1.0
             + stars(d, 155.0, 0.9450, 3.8) * belt * 1.6;
    col += vec3(0.92, 0.94, 1.0) * sk * 2.1 * fade;
  }

  float sd = max(dot(d, uSun), 0.0);
  col += vec3(0.86, 0.78, 1.0) * pow(sd, 5.0) * 0.13;

  vec3 qx = normalize(cross(uSun, vec3(0.0, 1.0, 0.0)));
  vec3 qy = cross(qx, uSun);
  vec2 q = vec2(dot(d, qx), dot(d, qy)) / uZoom;   // подлетаем — квазар растёт
  float qr = length(q);
  if (dot(d, uSun) > 0.0) {
    // ореол раскалённого газа
    col += vec3(0.72, 0.80, 1.0) * exp(-qr * 30.0) * 0.34;

    // джеты вдоль оси вращения
    float jet = exp(-pow(q.x / 0.0115, 2.0))
              * smoothstep(0.34, 0.05, abs(q.y)) * smoothstep(0.020, 0.045, abs(q.y));
    col += vec3(0.66, 0.84, 1.0) * jet * 1.15;

    // диск: сплюснутое кольцо, одна сторона ярче — доплеровское усиление
    float e = length(vec2(q.x, q.y / 0.24));
    float ring = exp(-pow((e - 0.058) / 0.0195, 2.0));
    float doppler = 0.45 + 0.95 * smoothstep(-0.035, 0.035, q.x);
    col += vec3(1.0, 0.66, 0.34) * ring * 3.4 * doppler;

    // изображение дальней стороны диска, задранное линзой над горизонтом
    float arc = exp(-pow((qr - 0.032) / 0.0075, 2.0)) * smoothstep(-0.004, 0.02, abs(q.y));
    col += vec3(1.0, 0.78, 0.52) * arc * 1.9;

    // ядро и сама тень
    col += vec3(1.0, 0.93, 0.84) * exp(-pow(qr / 0.030, 2.0)) * 0.42;
    col = mix(col, vec3(0.015, 0.014, 0.022), smoothstep(0.0215, 0.0155, qr));
  }

  float az = atan(d.z, d.x);

  // дальний хребет
  float r2 = 0.052 + 0.030 * ridge(az, 3.1);
  float m2 = smoothstep(r2 + 0.004, r2 - 0.004, h) * (1.0 - uSpace);
  col = mix(col, mix(uHaze, vec3(0.478, 0.430, 0.541), 0.62), m2);

  // ближний хребет
  float r1 = 0.030 + 0.024 * ridge(az * 1.31 + 1.7, 8.3);
  float m1 = smoothstep(r1 + 0.003, r1 - 0.003, h) * step(-0.02, h) * (1.0 - uSpace);
  col = mix(col, mix(uHaze, vec3(0.396, 0.335, 0.427), 0.80), m1);

  col = mix(col, uHaze, smoothstep(0.05, -0.02, h) * (1.0 - uSpace));   // в вакууме горизонта нет
  gl_FragColor = vec4(col, 1.0);
}`);

/* ---- песок: текстура с тропинками + мелкое зерно поверх ---- */

const groundProg = program(`
attribute vec3 aPos;
attribute vec3 aNormal;
uniform mat4 uVP;
varying vec3 vN;
varying vec3 vW;
void main() {
  vN = aNormal;
  vW = aPos;
  gl_Position = uVP * vec4(aPos, 1.0);
}`, PRECISION + `
varying vec3 vN;
varying vec3 vW;
uniform sampler2D uTex;
uniform vec3 uSun;
uniform vec3 uHaze;
uniform vec3 uCam;
uniform vec3 uLight;
uniform vec3 uAmb;
uniform float uExtent;
uniform float uTile;      // 1 — текстура повторяется по всему полю
uniform vec3 uGround;     // палитра мира: Невада или выжженный полигон
uniform float uFogK;

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

void main() {
  vec2 uv = vW.xz / uExtent + 0.5;
  if (uTile < 0.5) uv = clamp(uv, 0.001, 0.999);
  vec3 base = texture2D(uTex, uv).rgb;

  // зерно вблизи, чтобы песок не мылился под ногами
  float d = length(uCam - vW);
  float grain = (hash(floor(vW.xz * 26.0)) - 0.5) * 0.075 * (1.0 - smoothstep(2.0, 26.0, d));
  base += grain;

  vec3 N = normalize(vN);
  float ndl = max(dot(N, uSun), 0.0);
  vec3 sky = vec3(0.60, 0.68, 0.82) * (0.5 + 0.5 * N.y);
  vec3 col = base * uGround * (0.42 * sky * uAmb + ndl * uLight * 0.86);

  col = mix(col, uHaze, 1.0 - exp(-pow(d * uFogK, 2.0)));
  gl_FragColor = vec4(col, 1.0);
}`);

/* ---- монолитные объекты: столовые горы, камни, пирамидки ---- */

const solidProg = program(`
attribute vec3 aPos;
attribute vec3 aNormal;
attribute vec3 aColor;
uniform mat4 uVP;
uniform mat4 uModel;
varying vec3 vN;
varying vec3 vW;
varying vec3 vC;
void main() {
  vec4 w = uModel * vec4(aPos, 1.0);
  vN = mat3(uModel[0].xyz, uModel[1].xyz, uModel[2].xyz) * aNormal;
  vW = w.xyz; vC = aColor;
  gl_Position = uVP * w;
}`, PRECISION + `
varying vec3 vN;
varying vec3 vW;
varying vec3 vC;
uniform vec3 uSun;
uniform vec3 uHaze;
uniform vec3 uCam;
uniform vec3 uTint;
uniform vec3 uLight;
uniform vec3 uAmb;
uniform float uFogK;
void main() {
  vec3 N = normalize(vN);
  if (dot(N, uCam - vW) < 0.0) N = -N;          // грани валунов бывают вывернуты
  float ndl = max(dot(N, uSun), 0.0);
  vec3 sky = vec3(0.58, 0.66, 0.80) * (0.5 + 0.5 * N.y);
  vec3 bounce = vec3(0.86, 0.72, 0.54) * (0.5 - 0.5 * N.y);
  vec3 col = vC * uTint * ((0.60 * sky + 0.34 * bounce) * uAmb + ndl * uLight * 0.80);
  float d = length(uCam - vW);
  col = mix(col, uHaze, min(0.80, 1.0 - exp(-pow(d * uFogK, 2.0))));
  gl_FragColor = vec4(col, 1.0);
}`);

/* ---- спрайты: кусты полыни, подписи, тени под фигурами ---- */

const spriteProg = program(`
attribute vec3 aCenter;
attribute vec2 aCorner;
attribute vec2 aUv;
attribute float aPhase;
uniform mat4 uVP;
uniform vec3 uRight;
uniform vec3 uUp;
uniform float uMode;   // 0 — плоско на земле, 1 — вертикальный билборд, 2 — полный билборд
uniform float uTime;
uniform float uSway;
varying vec2 vUv;
varying vec3 vW;
void main() {
  vec3 p;
  if (uMode < 0.5) {
    p = aCenter + vec3(aCorner.x, 0.0, aCorner.y);
  } else if (uMode < 1.5) {
    vec3 r = normalize(vec3(uRight.x, 0.0, uRight.z));
    p = aCenter + r * aCorner.x + vec3(0.0, 1.0, 0.0) * aCorner.y;
    float s = sin(uTime * 1.6 + aPhase) + 0.4 * sin(uTime * 3.1 + aPhase * 1.7);
    p.xz += s * uSway * max(aCorner.y, 0.0);
  } else {
    p = aCenter + uRight * aCorner.x + uUp * aCorner.y;
  }
  vUv = aUv; vW = p;
  gl_Position = uVP * vec4(p, 1.0);
}`, PRECISION + `
varying vec2 vUv;
varying vec3 vW;
uniform sampler2D uTex;
uniform vec3 uHaze;
uniform vec3 uCam;
uniform float uAlphaTest;
uniform float uFade;
uniform vec3 uTint;
void main() {
  vec4 t = texture2D(uTex, vUv);
  if (t.a < uAlphaTest) discard;
  float d = length(uCam - vW);
  float fog = 1.0 - exp(-pow(d * ${FOG_K.toFixed(5)}, 2.0));
  vec3 col = mix(t.rgb * uTint, uHaze, fog);
  gl_FragColor = vec4(col, t.a * uFade);
}`);

/* ---- ленты: вся геометрия считается прямо в вершинном шейдере ----

   band(u, v, k, R) — точка поверхности: окружность радиуса R,
   поперёк неё отрезок, повёрнутый на k полуоборотов за круг.
   k = 0 — цилиндр, k = 1 — лента Мёбиуса, k = 2 — двойной перекрут.

   Кусок после разреза задаётся стороной uSide и щелью uGap.
   При uGap = 0 куски смыкаются и дают исходную фигуру.

   Расхождение кусков (uSpread) идёт поперёк ленты, вдоль её же кадра:
   куски остаются по разные стороны разреза на каждом u, а сама лента
   лежит в торе радиуса меньше uR — поэтому самопересечение невозможно
   ни в одном промежуточном положении ползунка.
*/

const bandProg = program(`
attribute float aU;
attribute float aS;

uniform mat4 uVP;
uniform mat4 uModel;
uniform float uK;
uniform float uR;
uniform float uW;
uniform float uGap;
uniform float uSide;
uniform float uSep;
uniform float uSpread;
uniform vec3 uOffset;

varying vec3 vN;
varying vec3 vW;
varying float vU;
varying float vS;

vec3 band(float u, float v, float k, float R) {
  float cu = cos(u), su = sin(u);
  vec3 C = vec3(cu, 0.0, su) * R;
  vec3 N = vec3(cu, 0.0, su);
  float a = k * u * 0.5;
  return C + v * (sin(a) * N + cos(a) * vec3(0.0, 1.0, 0.0));
}

vec3 shape(float u, float s) {
  float v0 = uGap * uW;
  float v = mix(v0, uW, s) + uSep * uSpread;
  // uOffset — только для незацепленных кусков (цилиндр), там перенос безопасен
  return band(u, v * uSide, uK, uR) + uOffset * uSep;
}

void main() {
  float du = 0.008, ds = 0.01;
  vec3 p  = shape(aU, aS);
  vec3 pu = shape(aU + du, aS);
  vec3 ps = shape(aU, aS + ds);
  vec3 n = normalize(cross(pu - p, ps - p)) * uSide;

  vec4 w = uModel * vec4(p, 1.0);
  vN = mat3(uModel[0].xyz, uModel[1].xyz, uModel[2].xyz) * n;
  vW = w.xyz;
  vU = aU;
  vS = aS;
  gl_Position = uVP * w;
}`, PRECISION + `
varying vec3 vN;
varying vec3 vW;
varying float vU;
varying float vS;

uniform vec3 uCam;
uniform vec3 uSun;
uniform vec3 uHaze;
uniform vec3 uLight;
uniform vec3 uAmb;
uniform vec3 uFaceA;
uniform vec3 uFaceB;
uniform vec3 uLine;
uniform float uProgress;
uniform float uLineFade;
uniform float uGap;
uniform float uWidth;

void main() {
  vec3 N = normalize(vN);
  vec3 V = normalize(uCam - vW);
  float facing = step(0.0, dot(N, V));
  if (facing < 0.5) N = -N;

  vec3 base = mix(uFaceB, uFaceA, facing);

  float ndl = max(dot(N, uSun), 0.0);
  vec3 sky = mix(vec3(0.52, 0.43, 0.34), vec3(0.60, 0.68, 0.83), N.y * 0.5 + 0.5);
  vec3 col = base * (sky * 0.62 * uAmb + ndl * uLight * 0.90);

  vec3 H = normalize(uSun + V);
  col += uLight * pow(max(dot(N, H), 0.0), 54.0) * 0.55;
  col += uHaze * pow(1.0 - max(dot(N, V), 0.0), 3.2) * 0.22;

  // средняя линия: живёт у самой кромки s = 0
  float un = fract(vU / ${TAU.toFixed(7)});
  float drawn = step(un, uProgress);
  float stripe = 1.0 - smoothstep(0.05, 0.11, vS);
  float ink = stripe * drawn * uLineFade;
  col = mix(col, uLine, clamp(ink * 0.92, 0.0, 1.0));
  col += uLine * ink * 0.35;

  // светящееся остриё там, где линия сейчас проводится
  float tip = exp(-pow((un - uProgress) * 46.0, 2.0)) * step(uProgress, 0.999) * uLineFade;
  col += uLine * tip * (1.0 - smoothstep(0.0, 0.34, vS)) * 1.2;

  // кромка разреза
  col += uLine * (1.0 - smoothstep(0.0, 0.035, vS)) * smoothstep(0.0, 0.25, uGap) * 0.55;

  float d = length(uCam - vW);
  col = mix(col, uHaze, 1.0 - exp(-pow(d * ${FOG_K.toFixed(5)}, 2.0)));
  gl_FragColor = vec4(col, 1.0);
}`);


/* ---- вода: рябь, отблеск квазара и круги от ладоней ---- */

const waterProg = program(`
attribute vec3 aPos;
uniform mat4 uVP;
varying vec3 vW;
void main() { vW = aPos; gl_Position = uVP * vec4(aPos, 1.0); }`, PRECISION + `
varying vec3 vW;
uniform vec3 uCam;
uniform vec3 uSun;
uniform vec3 uHaze;
uniform vec3 uLight;
uniform vec3 uAmb;
uniform vec2 uCenter;
uniform float uTime;
uniform float uSplash;
void main() {
  vec2 p = vW.xz - uCenter;
  float r = length(p);

  float w = sin(r * 22.0 - uTime * 2.4) * 0.5 + sin(p.x * 17.0 + uTime * 1.7) * 0.3
          + sin(p.y * 19.0 - uTime * 1.1) * 0.3;
  // круги от рук
  float sp = exp(-uSplash * 1.6) * sin(r * 26.0 - uSplash * 13.0) * smoothstep(1.8, 0.0, r - uSplash * 1.5);
  w += sp * 3.2;

  vec3 N = normalize(vec3(w * 0.055, 1.0, w * 0.045));
  vec3 V = normalize(uCam - vW);
  float fres = pow(1.0 - max(dot(N, V), 0.0), 3.0);
  vec3 H = normalize(uSun + V);

  vec3 deep = vec3(0.10, 0.18, 0.20);
  vec3 col = mix(deep, vec3(0.52, 0.63, 0.74), fres * 0.9 + 0.18) * (0.35 + 0.75 * uAmb);
  col += uLight * pow(max(dot(N, H), 0.0), 90.0) * 0.9;
  col += vec3(0.25, 0.32, 0.36) * max(w, 0.0) * 0.12;

  float d = length(uCam - vW);
  col = mix(col, uHaze, 1.0 - exp(-pow(d * ${FOG_K.toFixed(5)}, 2.0)));
  gl_FragColor = vec4(col, 1.0);
}`);

/* ---- пост-обработка: линзирование у чёрной дыры и метка замедления времени ----

   Свет, идущий мимо массы, отклоняется к ней: источник виден дальше от
   дыры, чем он есть. Значит для пикселя на угле r от центра сцену надо
   брать ближе к центру, на r - A/r. Отсюда кольцо Эйнштейна, растяжение
   вдоль радиуса и сжатие поперёк — всё разом.
*/

const postProg = program(`
attribute vec2 aPos;
varying vec2 vUv;
void main() { vUv = aPos * 0.5 + 0.5; gl_Position = vec4(aPos, 0.0, 1.0); }`, PRECISION + `
varying vec2 vUv;
uniform sampler2D uScene;
uniform float uAspect;
uniform vec2 uBH;
uniform float uShadow;
uniform float uVisible;
uniform float uDil;

void main() {
  vec2 d = (vUv - uBH) * vec2(uAspect, 1.0);
  float r = max(length(d), 1e-4);
  float A = uShadow * uShadow * 1.9 * uVisible;
  float shift = min(A / r, 0.30);
  vec2 suv = vUv - (d / r) * shift / vec2(uAspect, 1.0);
  vec3 col = texture2D(uScene, clamp(suv, vec2(0.0015), vec2(0.9985))).rgb;

  // фотонное кольцо и тень горизонта
  float ring = exp(-pow((r - uShadow * 1.13) / max(uShadow * 0.055, 1e-4), 2.0)) * uVisible;
  col += vec3(1.0, 0.89, 0.72) * ring * 0.75;
  col = mix(col, vec3(0.0), smoothstep(uShadow * 1.04, uShadow * 0.97, r) * uVisible);

  // чем сильнее расходятся часы, тем заметнее синий сдвиг и виньетка
  float t = clamp(log(max(uDil, 1.0)) / log(20.0), 0.0, 1.0);
  float grey = dot(col, vec3(0.30, 0.59, 0.11));
  col = mix(col, mix(col, vec3(grey) * vec3(0.74, 0.86, 1.18), 0.75), t);
  float vig = smoothstep(1.15, 0.30, length((vUv - 0.5) * vec2(uAspect, 1.0)));
  col *= mix(1.0, vig, t * 0.55);

  gl_FragColor = vec4(col, 1.0);
}`);

/* ---- нормали к средней линии: щетинка вдоль проведённого участка и стрелки ---- */

const normalProg = program(`
attribute vec3 aPos;
attribute vec3 aNormal;
attribute float aU;
uniform mat4 uVP;
uniform mat4 uModel;
varying vec3 vN;
varying vec3 vW;
varying float vU;
void main() {
  vec4 w = uModel * vec4(aPos, 1.0);
  vN = mat3(uModel[0].xyz, uModel[1].xyz, uModel[2].xyz) * aNormal;
  vW = w.xyz;
  vU = aU;
  gl_Position = uVP * w;
}`, PRECISION + `
varying vec3 vN;
varying vec3 vW;
varying float vU;
uniform vec3 uCam;
uniform vec3 uSun;
uniform vec3 uColor;
uniform float uProgress;
uniform float uFade;
void main() {
  if (vU > uProgress) discard;                 // ещё не проведённая часть линии
  vec3 N = normalize(vN);
  if (dot(N, uCam - vW) < 0.0) N = -N;
  float ndl = max(dot(N, uSun), 0.0);
  vec3 col = uColor * (0.70 + 0.45 * ndl);
  gl_FragColor = vec4(col, uFade);
}`);

/* ---- дальний план: планета под нами и соседи по системе ----

   Рисуются в системе камеры: реальные расстояния измеряются миллионами
   километров, поэтому объект ставится на фиксированном удалении, а его
   угловой размер считается честно — из высоты полёта. Глубина прижата к
   дальней плоскости, так что ландшафт и ракета их закрывают.
*/

const planetProg = program(`
attribute vec3 aPos;
attribute vec2 aUv;
uniform mat4 uVP;
uniform vec3 uCenter;
uniform float uRadius;
uniform mat4 uRot;
varying vec2 vUv;
varying vec3 vN;
varying vec3 vLocal;
void main() {
  vec3 n = (uRot * vec4(aPos, 0.0)).xyz;
  vN = n;
  vLocal = aPos;          // направление в системе самой планеты
  vUv = aUv;
  vec4 clip = uVP * vec4(uCenter + n * uRadius, 1.0);
  clip.z = clip.w * 0.99999;          // почти дальняя плоскость
  gl_Position = clip;
}`, PRECISION + PLANET_NOISE + `
varying vec2 vUv;
varying vec3 vN;
varying vec3 vLocal;
uniform sampler2D uTex;
uniform vec3 uSun;
uniform vec3 uColor;
uniform float uMode;      // 0 — планета с текстурой, 1 — сосед, 2 — кольцо
uniform float uFade;
uniform vec3 uRim;        // направление «прямо на камеру» из центра планеты
uniform float uNear;      // 1, когда планета раскрыта под нами во весь экран
uniform float uCloud;     // плотность облачного слоя
uniform float uLimb;      // косинус края видимой шапки: за ним начинается силуэт
uniform float uTime;
void main() {
  vec3 N = normalize(vN);
  float ndl = dot(N, uSun);
  float day = smoothstep(-0.12, 0.22, ndl);          // мягкий терминатор

  vec3 base;
  if (uMode < 0.5) {
    // UV считаем прямо из направления — той же формулой, что и в генераторе,
    // иначе развёртка сетки и текстуры расходятся
    vec3 L = normalize(vLocal);
    vec2 uv = vec2(atan(L.z, L.x) * 0.1591549 + 0.5, asin(clamp(L.y, -1.0, 1.0)) * 0.3183099 + 0.5);
    vec4 t = texture2D(uTex, uv);
    base = t.rgb;
    float dry = smoothstep(0.02, 0.22, t.a);      // 0 — вода, 1 — суша
    /* Вблизи один тексель карты растягивается на пол-экрана. Дорисовываем
       два масштаба рельефа поверх: суша получает складки и рощи, вода —
       бегущую рябь с бликами. Подмешивается плавно по uNear. */
    if (uNear > 0.01) {
      float d1 = fbm3(L * 780.0);
      float d2 = fbm3(L * 3300.0);
      vec3 solid = base * (1.0 + ((d1 - 0.5) * 1.30 + (d2 - 0.5) * 0.80) * 0.62);
      float w = fbm3(L * 1250.0 + vec3(uTime * 0.05, 0.0, uTime * 0.03));
      vec3 sea = base * (0.84 + 0.36 * w) + vec3(0.10, 0.13, 0.15) * pow(w, 8.0) * 3.0;
      base = mix(base, mix(sea, solid, dry), uNear);
    }
    // облачный слой живёт отдельно от карты и тает при подходе к земле
    float cf = (1.0 - uNear) * uCloud;
    if (cf > 0.01) {
      vec3 cq = L * 3.6 + vec3(uTime * 0.0035, 0.0, uTime * 0.0018);
      float c = fbm3(cq) * 0.72 + fbm3(cq * 3.1) * 0.28;
      // крупная маска оставляет широкие просветы — иначе шар затянут сплошь
      float open = smoothstep(0.34, 0.62, fbm3(L * 1.5 + vec3(19.0)));
      base = mix(base, vec3(0.93, 0.95, 0.98), smoothstep(0.56, 0.80, c) * open * 0.80 * cf);
    }
  } else if (uMode < 1.5) {
    float band = sin(N.y * 9.0) * 0.5 + 0.5;
    base = uColor * (0.82 + 0.28 * band);
  } else {
    float t = fract(vUv.x * 7.0);
    base = uColor * (0.55 + 0.45 * step(0.35, t));
  }

  vec3 col = base * (0.06 + 0.98 * day);
  /* Атмосферный ободок жмётся к силуэту. Видимая шапка кончается там, где
     dot(N, uRim) падает до uLimb, — от этой границы и считаем, иначе свечение
     заливает половину диска белым. */
  float lim = clamp((dot(N, uRim) - uLimb) / max(1.0 - uLimb, 0.02), 0.0, 1.0);
  float rim = pow(1.0 - lim, 7.0);
  col += vec3(0.30, 0.52, 0.95) * rim * day * (uMode < 0.5 ? 0.55 : 0.0);
  gl_FragColor = vec4(col, uFade);
}`);

/* ---- точки: рождение и аннигиляция пар у горизонта ---- */

const pointProg = program(`
attribute vec3 aPos;
attribute vec4 aColor;
uniform mat4 uVP;
uniform vec3 uCam;
uniform float uScale;
varying vec4 vCol;
void main() {
  vCol = aColor;
  vec4 clip = uVP * vec4(aPos, 1.0);
  float d = length(uCam - aPos);
  gl_PointSize = clamp(uScale / max(d, 0.5), 2.0, 26.0);
  gl_Position = clip;
}`, PRECISION + `
varying vec4 vCol;
void main() {
  vec2 q = gl_PointCoord - 0.5;
  float r = length(q);
  if (r > 0.5) discard;
  float glow = pow(1.0 - r * 2.0, 1.6);
  gl_FragColor = vec4(vCol.rgb * (0.55 + 0.9 * glow), vCol.a * glow);
}`);
