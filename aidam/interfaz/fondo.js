/* AIDAM — fondo ambiental "hielo glacial" (WebGL, autocontenido).
 *
 * Capa decorativa muy sutil bajo la interfaz: ruido simplex lento entre
 * obsidiana y azul glacial con destellos de agua. Si WebGL no está o el
 * usuario prefiere menos movimiento, queda el degradado estático del CSS.
 */

"use strict";

(function () {
  const canvas = document.getElementById("fondo");
  if (!canvas) return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

  const gl = canvas.getContext("webgl");
  if (!gl) return;

  function ajustar() {
    const w = canvas.clientWidth || innerWidth;
    const h = canvas.clientHeight || innerHeight;
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
  }
  new ResizeObserver(ajustar).observe(canvas);
  ajustar();

  const vs = `attribute vec2 a; varying vec2 v;
    void main(){ v = a * 0.5 + 0.5; gl_Position = vec4(a, 0.0, 1.0); }`;

  const fs = `precision highp float;
    varying vec2 v; uniform float t;
    vec3 mod289(vec3 x){ return x - floor(x * (1.0/289.0)) * 289.0; }
    vec2 mod289(vec2 x){ return x - floor(x * (1.0/289.0)) * 289.0; }
    vec3 permute(vec3 x){ return mod289(((x*34.0)+1.0)*x); }
    float snoise(vec2 p){
      const vec4 C = vec4(0.211324865405187, 0.366025403784439, -0.577350269189626, 0.024390243902439);
      vec2 i = floor(p + dot(p, C.yy));
      vec2 x0 = p - i + dot(i, C.xx);
      vec2 i1 = (x0.x > x0.y) ? vec2(1.0, 0.0) : vec2(0.0, 1.0);
      vec4 x12 = x0.xyxy + C.xxzz; x12.xy -= i1;
      i = mod289(i);
      vec3 q = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));
      vec3 m = max(0.5 - vec3(dot(x0,x0), dot(x12.xy,x12.xy), dot(x12.zw,x12.zw)), 0.0);
      m = m*m; m = m*m;
      vec3 x = 2.0 * fract(q * C.www) - 1.0;
      vec3 h = abs(x) - 0.5;
      vec3 a0 = x - floor(x + 0.5);
      m *= 1.79284291400159 - 0.85373472095314 * (a0*a0 + h*h);
      vec3 g;
      g.x = a0.x * x0.x + h.x * x0.y;
      g.yz = a0.yz * x12.xz + h.yz * x12.yw;
      return 130.0 * dot(m, g);
    }
    void main(){
      float n = snoise(v * 3.0 + t * 0.05);
      n += 0.5 * snoise(v * 6.0 - t * 0.1);
      vec3 obsidiana = vec3(0.02, 0.028, 0.04);
      vec3 glacial = vec3(0.44, 0.82, 1.0);
      vec3 color = mix(obsidiana, glacial, n * 0.16 + 0.08);
      float destello = pow(max(0.0, snoise(v * 10.0 + t * 0.25)), 12.0);
      color += destello * 0.22;
      gl_FragColor = vec4(color, 1.0);
    }`;

  function compilar(tipo, fuente) {
    const s = gl.createShader(tipo);
    gl.shaderSource(s, fuente);
    gl.compileShader(s);
    return s;
  }

  const programa = gl.createProgram();
  gl.attachShader(programa, compilar(gl.VERTEX_SHADER, vs));
  gl.attachShader(programa, compilar(gl.FRAGMENT_SHADER, fs));
  gl.linkProgram(programa);
  if (!gl.getProgramParameter(programa, gl.LINK_STATUS)) return;
  gl.useProgram(programa);

  const buf = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const pos = gl.getAttribLocation(programa, "a");
  gl.enableVertexAttribArray(pos);
  gl.vertexAttribPointer(pos, 2, gl.FLOAT, false, 0, 0);
  const uT = gl.getUniformLocation(programa, "t");

  (function pintar(ms) {
    ajustar();
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.uniform1f(uT, ms * 0.001);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    requestAnimationFrame(pintar);
  })(0);
})();
