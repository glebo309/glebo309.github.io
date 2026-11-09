// Normalize wheel units and keep zoom reversible at every event size.
export function wheelZoomFactor(delta,mode=0,height=600){
 const pixels=delta*(mode===1?16:mode===2?height:1);
 return Math.exp(Math.max(-700,Math.min(700,pixels))*.0035);
}
