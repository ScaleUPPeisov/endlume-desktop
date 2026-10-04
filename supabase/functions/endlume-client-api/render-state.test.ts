import { shouldIgnoreRenderMutation } from "./render-state.ts";

function assert(value:boolean,label:string){if(!value)throw new Error(label)}

Deno.test("failed is terminal against late progress",()=>{assert(shouldIgnoreRenderMutation("failed","render_progress"),"failed resurrected");});
Deno.test("completed is terminal against late progress",()=>{assert(shouldIgnoreRenderMutation("completed","render_progress"),"completed resurrected");});
Deno.test("cancelled is terminal against late progress",()=>{assert(shouldIgnoreRenderMutation("cancelled","render_progress"),"cancelled resurrected");});
Deno.test("blocked is terminal against late start and stage",()=>{
  assert(shouldIgnoreRenderMutation("blocked","render_started"),"blocked start resurrected");
  assert(shouldIgnoreRenderMutation("blocked","render_stage"),"blocked stage resurrected");
});
Deno.test("rendering accepts progress and terminal events are not suppressed",()=>{
  assert(!shouldIgnoreRenderMutation("rendering","render_progress"),"valid progress suppressed");
  assert(!shouldIgnoreRenderMutation("failed","render_failed"),"terminal event wrongly suppressed");
});
