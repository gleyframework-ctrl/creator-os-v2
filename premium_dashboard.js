(function(){
setInterval(function(){
var c=document.getElementById('premium-dashboard'),b=document.getElementById('dashboard-content');
if(!c||!b||!b.innerHTML||b.innerHTML.includes('skeleton'))return;
var jd=window.journeyData||{},td=jd.tasks_completed_count||0,tt=12,xp=jd.xp||0,st=jd.streak||0,avg=jd.avg_score||0;
var hs=Math.min(100,Math.round((td/tt)*40+Math.min(st,30)+Math.min(xp/100,20)+(avg/10)*10));
var hc=hs>=70?'text-emerald-400':hs>=40?'text-amber-400':'text-red-400';
var hl=hs>=70?'Strong':hs>=40?'Building':'At Risk';
var pr=Math.round((td/tt)*100);
c.innerHTML='<div class="grid grid-cols-1 md:grid-cols-2 gap-4">'
+'<div class="glass p-5 rounded-2xl"><div class="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Health Score</div>'
+'<div class="text-3xl font-semibold '+hc+' mt-2">'+hs+'</div>'
+'<div class="text-sm text-white">'+hl+'</div>'
+'<div class="text-xs text-slate-500 mt-1">Tasks · Streak · XP · Grading</div></div>'
+'<div class="glass p-5 rounded-2xl"><div class="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-500">Journey Progress</div>'
+'<div class="text-3xl font-semibold text-white mt-1">'+pr+'%</div>'
+'<div class="h-2 bg-slate-800 rounded-full overflow-hidden mt-3"><div class="h-full bg-gradient-to-r from-purple-500 to-pink-500" style="width:'+pr+'%"></div></div>'
+'<div class="text-xs text-slate-500 mt-2">'+td+' of '+tt+' tasks complete</div></div>'
+'</div>';
},600);
})();
