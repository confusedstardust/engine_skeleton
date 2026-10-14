"use client";
import * as Dialog from "@radix-ui/react-dialog";
import * as ToggleGroup from "@radix-ui/react-toggle-group";
import * as Tabs from "@radix-ui/react-tabs";
import {useEffect,useState} from "react";
import {attributeGroups} from "./asset-attribute-groups";
import {withBasePath} from "../app/base-path";
type Vocabulary=Record<string,{attributes:Record<string,string[]>}>;
const kinds=[{value:"BACKGROUND",label:"背景"},{value:"FIGURE",label:"立绘"},{value:"BGM",label:"BGM"}];
export default function AdminAssetUpload({onUploaded}:{onUploaded:()=>void}) {
 const [open,setOpen]=useState(false),[filename,setFilename]=useState("");
 const [kind,setKind]=useState("BACKGROUND"),[attributes,setAttributes]=useState<Record<string,string[]>>({}),[busy,setBusy]=useState(false),[message,setMessage]=useState("");
 const [vocabulary,setVocabulary]=useState<Vocabulary>({}),[drafts,setDrafts]=useState<Record<string,string>>({}),[adding,setAdding]=useState("");
 useEffect(()=>{if(!open)return;let active=true;
   fetch(withBasePath("/api/forge/admin/assets/taxonomy"),{credentials:"include"}).then(async r=>{if(!r.ok)throw new Error("属性选项加载失败");return r.json();}).then(data=>{if(active)setVocabulary(old=>{const next={...old};for(const k of kinds){const values={...(old[k.value]?.attributes||{})};for(const [key,options] of Object.entries(data[k.value]?.attributes||{}))values[key]=Array.from(new Set([...(values[key]||[]),...(options as string[])]));next[k.value]={attributes:values};}return next;});}).catch(e=>{if(active)setMessage(e.message);});return()=>{active=false;};
 },[open]);
 function choose(key:string,values:string[]) {setAttributes(old=>({...old,[key]:values}));}
 function addChoice(key:string,multiple:boolean) {
   const text=(drafts[key]||"").trim();if(!text)return;
   setVocabulary(old=>({...old,[kind]:{attributes:{...(old[kind]?.attributes||{}),[key]:Array.from(new Set([...(old[kind]?.attributes?.[key]||[]),text]))}}}));
   choose(key,multiple?Array.from(new Set([...(attributes[key]||[]),text])):[text]);setDrafts(old=>({...old,[key]:""}));setAdding("");
 }
 async function submit(e:React.FormEvent<HTMLFormElement>) {
 e.preventDefault();const form=e.currentTarget;const data=new FormData(form);data.set("kind",kind);data.set("attributes",JSON.stringify(attributes));setBusy(true);setMessage("");
 try {const response=await fetch(withBasePath("/api/forge/admin/assets/upload"),{method:"POST",credentials:"include",headers:{"X-Forge-Admin-Action":"1"},body:data});const body=await response.json();if(!response.ok)throw new Error(body.detail||"上传失败");form.reset();setFilename("");setAttributes({});setMessage("上传成功，已加入公共素材库");onUploaded();setOpen(false);}catch(error){setMessage(error instanceof Error?error.message:"上传失败");}finally{setBusy(false);}
 }
 return <Dialog.Root open={open} onOpenChange={value=>{if(!busy){setOpen(value);if(value)setMessage("");}}}>
 <div className="admin-upload-entry"><Dialog.Trigger asChild><button className="btn outline" type="button"><span aria-hidden="true">＋</span> 上传公共素材</button></Dialog.Trigger>{message&&!open?<span role="status">{message}</span>:null}</div>
 <Dialog.Portal><Dialog.Overlay className="radix-confirm-overlay"/><Dialog.Content className="admin-upload-dialog" aria-describedby="admin-upload-description" onEscapeKeyDown={e=>{if(busy)e.preventDefault();}} onPointerDownOutside={e=>{if(busy)e.preventDefault();}}>
 <header className="asset-modal-head"><Dialog.Title>上传公共素材</Dialog.Title><Dialog.Close asChild><button type="button" aria-label="关闭上传" disabled={busy}>×</button></Dialog.Close></header>
 <form onSubmit={submit}><div className="admin-upload-body"><Dialog.Description id="admin-upload-description">添加到平台素材库，供用户浏览、收藏和选用。</Dialog.Description><fieldset disabled={busy}>
 <Tabs.Root value={kind} onValueChange={v=>{setKind(v);setAttributes({});setFilename("");setDrafts({});setAdding("");}}><Tabs.List className="admin-upload-types" aria-label="素材类型">{kinds.map(k=><Tabs.Trigger key={k.value} value={k.value} disabled={busy}>{k.label}</Tabs.Trigger>)}</Tabs.List></Tabs.Root>
 <div className="admin-upload-fields"><label className="admin-upload-name">素材名称<input name="name" placeholder="输入用户看到的素材名称" required maxLength={200}/></label></div>
 <label className="admin-upload-file"><input key={kind} name="file" type="file" required disabled={busy} aria-label="选择素材文件" accept={kind==="BACKGROUND"||kind==="FIGURE"?"image/png,image/jpeg,image/webp":".mp3,.wav,.ogg,.m4a"} onChange={e=>setFilename(e.target.files?.[0]?.name||"")}/><span className="admin-upload-file-icon" aria-hidden="true">↑</span><strong>{filename||"点击选择文件"}</strong><span>{kind==="BACKGROUND"||kind==="FIGURE"?"PNG、JPEG、WebP":"MP3、WAV、OGG、M4A"} · 最大 30 MB</span></label>
 <section className="admin-attribute-section" aria-label="素材属性"><div className="admin-upload-tag-heading">素材属性<span>按需填写</span></div>{(attributeGroups[kind]||[]).map(group=>{
 const options=Array.from(new Set([...group.options,...(vocabulary[kind]?.attributes?.[group.key]||[])]));
 const items=options.map(value=><ToggleGroup.Item key={value} value={value}>{value}</ToggleGroup.Item>);
 return <div className="admin-attribute-row" key={group.key}><div className="admin-attribute-label"><strong>{group.label}</strong><span>{group.multiple?"多选":"单选"}</span></div><div className="admin-attribute-options">{group.multiple?<ToggleGroup.Root className="admin-upload-tags" type="multiple" value={attributes[group.key]||[]} onValueChange={v=>choose(group.key,v)} disabled={busy} aria-label={group.label}>{items}</ToggleGroup.Root>:<ToggleGroup.Root className="admin-upload-tags" type="single" value={attributes[group.key]?.[0]||""} onValueChange={v=>choose(group.key,v?[v]:[])} disabled={busy} aria-label={group.label}>{items}</ToggleGroup.Root>}
 {adding===group.key?<div className="admin-upload-add"><input autoFocus value={drafts[group.key]||""} maxLength={40} aria-label={`新增${group.label}`} placeholder={`添加${group.label}选项`} onChange={e=>setDrafts(old=>({...old,[group.key]:e.target.value}))} onKeyDown={e=>{if(e.key==="Enter"){e.preventDefault();addChoice(group.key,group.multiple);}}}/><button className="btn outline" type="button" disabled={busy||!drafts[group.key]?.trim()} onClick={()=>addChoice(group.key,group.multiple)}>添加</button><button className="btn outline" type="button" onClick={()=>setAdding("")}>取消</button></div>:<button className="admin-attribute-add" type="button" disabled={busy} onClick={()=>setAdding(group.key)}>＋ 添加{group.label}</button>}
 </div></div>;
 })}</section>
 </fieldset>{message?<p className="admin-upload-message" role="alert">{message}</p>:null}</div><footer className="asset-modal-actions"><Dialog.Close asChild><button className="btn outline" type="button" disabled={busy}>取消</button></Dialog.Close><button className="btn primary" disabled={busy}>{busy?"正在上传…":"上传素材"}</button></footer></form>
 </Dialog.Content></Dialog.Portal></Dialog.Root>;
}
