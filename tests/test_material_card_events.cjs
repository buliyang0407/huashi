const {test}=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs');
test('quoted filenames remain data for view, bag, copy and image selection',()=>{
 const nodes=new Map();const document={querySelector(s){if(!nodes.has(s))nodes.set(s,{innerHTML:'',style:{}});return nodes.get(s)},body:{style:{}},addEventListener(){}};
 const c=vm.createContext({document,event:{target:null},URLSearchParams,location:{search:'',origin:'http://local'},fetch:()=>new Promise(()=>{}),setTimeout(){},clearTimeout(){},events:[]});
 const source=fs.readFileSync('web/portrait-studio.html','utf8').split('<script>')[1].split('</script>')[0];vm.runInContext(source,c);
 const id="pose:a');globalThis.__reviewInjected=1;('b.png";const m={id,title:"O'Brien",words:'reference',source:'fixture',category:'姿势',image:'/pose-files/example.png'};
 vm.runInContext('materials='+JSON.stringify([m])+';pick=0;detail(materials[0].id,false)',c);
 const detail=nodes.get('#detail').innerHTML;
 const cards=[vm.runInContext('card(materials[0],false)',c),vm.runInContext('card(materials[0],true)',c),detail];
 vm.runInContext("detail=id=>events.push(['view',id]);toggle=id=>events.push(['bag',id]);copyCard=id=>events.push(['copy',id]);choose=id=>events.push(['select',id]);closeDetail=()=>{};copyWords=()=>{}",c);
 for(const html of cards)for(const match of html.matchAll(/onclick="([^"]*)"/g)){
  const code=match[1].replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&amp;/g,'&');
  assert.ok(!code.includes('__reviewInjected'));vm.runInContext(code,c);
 }
 assert.equal(c.__reviewInjected,undefined);assert.ok(c.events.length>=8);for(const event of c.events)assert.equal(event[1],id);
 for(const action of ['view','bag','copy','select'])assert.ok(c.events.some(e=>e[0]===action));
});
