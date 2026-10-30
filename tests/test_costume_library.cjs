const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const context = {window:{}};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../web/rooms.js'),'utf8'),context);
const rooms=context.window.HuashiRooms;
test('costume folder is separate from pose and stays read-only',()=>{
 const input=[{id:'works',name:'作品'},{id:'__pose__',name:'POSE',virtual:true,directory_count:4}];
 const actual=rooms.displayFolders(input).find(f=>f.id==='__costumes__');
 assert.ok(actual && !actual.placeholder,'服装库入口应可用');
 assert.equal(actual.displayName,'服装库');assert.equal(actual.virtual,true);
 assert.equal(actual.directory_count,8);assert.equal(input.length,2);
 assert.equal(rooms.displayFolders(input).filter(f=>f.id==='__pose__').length,1);
 assert.equal(rooms.displayFolders(input).find(f=>f.id==='__pose__').directory_count,3);
 assert.equal(input[1].directory_count,4);
});
test('directory paths stay under independent costume root',()=>{
 assert.equal(rooms.directoryPath('__costumes__',''),'.costume-library');
 assert.equal(rooms.directoryPath('__costumes__','春装'),'.costume-library/春装');
 assert.equal(rooms.directoryPath('__pose__','AI姿势参考/标准'),'AI姿势参考/标准');
 for(const bad of ['../SFWPose','/SFWPose','春装/../../SFWPose','春装\\..\\SFWPose'])
  assert.throws(()=>rooms.directoryPath('__costumes__',bad));
});
test('costume breadcrumb round trips and preserves image input identity',()=>{
 const raw={path:'.costume-library/春装',name:'春装',directories:[],
 breadcrumbs:[{name:'.costume-library',path:'.costume-library'},{name:'春装',path:'.costume-library/春装'}],
 items:[{id:'pose:.costume-library/春装/SPR-0001.png',path:'pose:.costume-library/春装/SPR-0001.png',pose_path:'.costume-library/春装/SPR-0001.png'}]};
 const normalized=rooms.directoryData('__costumes__',raw);
 assert.equal(normalized.path,'春装');assert.equal(normalized.breadcrumbs.length,1);
 assert.equal(normalized.breadcrumbs[0].path,'春装');
 assert.equal(normalized.items[0].path,raw.items[0].path);
 assert.equal(raw.breadcrumbs.length,2);
 const root=rooms.directoryData('__costumes__',{path:'.costume-library',breadcrumbs:[{name:'.costume-library',path:'.costume-library'}],directories:[{name:'春装',path:'.costume-library/春装'}],items:[]});
 assert.equal(root.name,'服装库');assert.equal(root.directories[0].path,'春装');assert.equal(root.breadcrumbs.length,0);
 assert.equal(rooms.directoryPath('__costumes__',root.directories[0].path),'.costume-library/春装');
 assert.throws(()=>rooms.directoryData('__costumes__',{path:'SFWPose',directories:[],breadcrumbs:[],items:[]}));
});
test('old pose directory data is unchanged',()=>{
 const data={path:'SFWPose',breadcrumbs:[],directories:[],items:[]};
 assert.equal(rooms.directoryData('__pose__',data),data);
 assert.equal(rooms.directoryLibrary('__costumes__').label,'服装库');
 assert.equal(rooms.directoryLibrary('__faces__'),null);
});
test('costume categories keep the upstream browsing order',()=>{
 const result=rooms.directoryData('__costumes__',{path:'.costume-library',items:[],breadcrumbs:[],directories:['冬装','内衣','夏装','春装'].map(name=>({name,path:'.costume-library/'+name}))});
 assert.equal(result.directories.map(d=>d.name).join(','),'春装,夏装,冬装,内衣');
});
