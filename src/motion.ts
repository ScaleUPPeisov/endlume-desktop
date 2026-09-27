/* ENDLUME Motion Runtime v2.
   Intentionally empty: scrolling and interaction stay fully native in macOS WKWebView.
   Do not attach wheel/scroll listeners or a per-frame FPS governor here. */
export function installMotionRuntime(){
  return ()=>{};
}
