"""Browser independent prompt directory scope and save contracts."""
import subprocess
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
class PromptFolderUITests(unittest.TestCase):
    def test_leaf_default_remembrance_and_explicit_all_scope(self):
        script = r"""
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');global.window={};
assert.ok(fs.existsSync('web/prompt-folders.js'),'shared directory module must exist');
vm.runInThisContext(fs.readFileSync('web/prompt-folders.js','utf8'));
const f=window.HuashiPromptFolders;
const data={folders:[{id:'parent',level:1},{id:'default',parent_id:'parent',level:2},{id:'poses',parent_id:'parent',level:2}],default_folder_id:'default'};
assert.equal(f.resolveLeaf(data,'poses'),'poses');
assert.equal(f.resolveLeaf(data,'parent'),'default');
assert.equal(f.resolveLeaf(data,'removed'),'default');
assert.equal(f.resolveLeaf({folders:[],default_folder_id:'bad'},''),'');
const prompts=[{id:'a',folder_id:'default'},{id:'b',folder_id:'poses'}];
assert.deepEqual(f.filterPrompts(prompts,'default',false),[prompts[0]]);
assert.deepEqual(f.filterPrompts(prompts,'',false),[]);
assert.deepEqual(f.filterPrompts(prompts,'default',true),prompts);
vm.runInThisContext(fs.readFileSync('web/creation-links.js','utf8'));
const saved=window.HuashiCreation.promptPayload('新稿','正文','poses','分类:旧标签, 人像, 人像');
assert.equal(window.HuashiCreation.promptPayload('人像','正文','poses','人像','原有负面提示词').note,'原有负面提示词');
assert.equal(saved.folder_id,'poses');assert.deepEqual(saved.tags,['分类:旧标签','人像']);
vm.runInThisContext(fs.readFileSync('web/room-search.js','utf8'));
const search=window.HuashiSearch;
assert.equal(search.folderFilter({kind:'prompt',promptFolderId:'poses',allDirectories:false},false),'poses');
assert.equal(search.folderFilter({kind:'all',promptFolderId:'poses',allDirectories:false},false),'');
assert.equal(search.folderFilter({kind:'all',promptFolderId:'poses',allDirectories:false},true),'poses');
assert.equal(search.folderFilter({kind:'prompt',promptFolderId:'poses',allDirectories:true},true),'');
"""
        result = subprocess.run(['node','-e',script],cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stderr)
