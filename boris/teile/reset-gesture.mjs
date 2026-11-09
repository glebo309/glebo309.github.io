export function bindResetGesture(target,reset){
 target.addEventListener('dblclick',event=>{event.preventDefault();reset();});
}
