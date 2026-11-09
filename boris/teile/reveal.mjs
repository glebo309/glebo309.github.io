export function createReveal(duration=7000){
 let elapsed=0,last=null,progress=0;
 return {update(now,visible,reduced=false){
  if(progress===1)return 1;
  if(!visible){last=null;return progress;}
  if(reduced)return progress=1;
  if(last!==null)elapsed+=Math.max(0,now-last);
  last=now;const t=Math.min(1,elapsed/duration);return progress=t*t*(3-2*t);
 }};
}
