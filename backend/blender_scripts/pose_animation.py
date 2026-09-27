import bpy,hashlib,json,math,re,sys,traceback
from pathlib import Path
from mathutils import Euler,Vector
RESULT_PREFIX='BODIEZ_RESULT:'
SEM={'hips':{'hips','pelvis'},'spine':{'spine'},'spine1':{'spine1','spine01'},'spine2':{'spine2','spine02'},'neck':{'neck'},'head':{'head'},'left_shoulder':{'leftshoulder','lshoulder','shoulderl'},'right_shoulder':{'rightshoulder','rshoulder','shoulderr'},'left_upper_arm':{'leftarm','leftupperarm','upperarml'},'right_upper_arm':{'rightarm','rightupperarm','upperarmr'},'left_forearm':{'leftforearm','leftlowerarm','lowerarml'},'right_forearm':{'rightforearm','rightlowerarm','lowerarmr'},'left_hand':{'lefthand','handl'},'right_hand':{'righthand','handr'},'left_thigh':{'leftupleg','leftthigh','thighl'},'right_thigh':{'rightupleg','rightthigh','thighr'},'left_shin':{'leftleg','leftlowerleg','calfl','shinl'},'right_shin':{'rightleg','rightlowerleg','calfr','shinr'},'left_foot':{'leftfoot','footl'},'right_foot':{'rightfoot','footr'},'left_toe':{'lefttoebase','lefttoe','toel'},'right_toe':{'righttoebase','righttoe','toer'}}
CORE={'hips','head','left_upper_arm','right_upper_arm','left_forearm','right_forearm','left_thigh','right_thigh','left_shin','right_shin','left_foot','right_foot'}
def norm(n):
 v=n.replace('\\','/').split('/')[-1].split('|')[-1].rsplit(':',1)[-1];v=re.sub(r'[^A-Za-z0-9]','',v).lower();return v[10:] if v.startswith('mixamorig') else v
def semmap(a):
 lookup={norm(b.name):b.name for b in a.data.bones};out={}
 for k,vs in SEM.items():
  for v in vs:
   if v in lookup:out[k]=lookup[v];break
 return out
def meshes(a):return [o for o in bpy.context.scene.objects if o.type=='MESH' and (o.parent==a or any(m.type=='ARMATURE' and m.object==a for m in o.modifiers))]
def armature(objs=None):
 aa=[o for o in (objs or bpy.context.scene.objects) if o.type=='ARMATURE']
 if not aa:raise RuntimeError('Nenhum armature encontrado.')
 def score(a):s=semmap(a);return(sum(k in s for k in CORE),len(meshes(a)),len(a.data.bones))
 return max(aa,key=score)
def target_objects(a):
 out=[a,*meshes(a)];p=a.parent
 while p and p.type=='EMPTY':
  if p not in out:out.append(p)
  p=p.parent
 return out
def export(path,a):
 Path(path).parent.mkdir(parents=True,exist_ok=True);bpy.ops.object.select_all(action='DESELECT')
 for o in target_objects(a):
  if o and o.name in bpy.context.scene.objects:
   try:o.select_set(True)
   except RuntimeError:pass
 bpy.context.view_layer.objects.active=a;bpy.ops.export_scene.gltf(filepath=str(path),export_format='GLB',use_selection=True,export_yup=True,export_skins=True,export_morph=True,export_animations=True,export_cameras=False,export_lights=False)
def signature(a):return hashlib.sha256('\n'.join(f'{b.name}|{b.parent.name if b.parent else ""}|{int(b.use_deform)}' for b in a.data.bones).encode()).hexdigest()[:24]
def bone_rows(a):
 s=semmap(a);rev={v:k for k,v in s.items()};return [{'name':b.name,'parent':b.parent.name if b.parent else None,'deform':bool(b.use_deform),'semantic':rev.get(b.name),'length':round(float(b.length),6)} for b in a.data.bones]
def structural(a):
 changed=False;bones=[]
 for p in a.pose.bones:
  loc,rot,sc=p.matrix_basis.decompose()
  if loc.length>1e-6 or rot.angle>1e-6 or any(abs(v-1)>1e-6 for v in sc):changed=True;bones.append(p.name)
 roots=[];o=a.parent
 while o:
  if any(abs(v-1)>1e-6 for v in o.scale):changed=True;roots.append(o.name)
  o=o.parent
 return {'present':changed,'bones_with_offsets':bones,'scaled_parent_objects':roots}
def prep(src,blend,preview,report):
 bpy.ops.wm.open_mainfile(filepath=src,load_ui=False);a=armature();a.data.pose_position='POSE'
 if a.animation_data:a.animation_data.action=None
 data={'armature':a.name,'target_signature':signature(a),'bones':bone_rows(a),'semantic_matches':semmap(a),'structural_layer':structural(a),'pose_limits_degrees':[-180,180],'pose_reference':'current_body_reference','limitations':['A edição de pose usa rotações locais; IK e constraints específicos de rigs proprietários não são inferidos.','A pose de referência preserva as proporções corporais atuais em vez de reescrever a rest pose.']};Path(report).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');bpy.ops.wm.save_as_mainfile(filepath=blend);export(preview,a)
def pose_apply(base,request,blend,preview,report):
 bpy.ops.wm.open_mainfile(filepath=base,load_ui=False);a=armature();q=json.loads(Path(request).read_text(encoding='utf-8'));ap=[]
 for name,axes in q.get('rotations_degrees',{}).items():
  p=a.pose.bones.get(name)
  if not p:raise RuntimeError(f'Osso não encontrado: {name}')
  loc,br,sc=p.matrix_basis.decompose();delta=Euler(tuple(math.radians(float(axes.get(k,0))) for k in ('x','y','z')),'XYZ').to_quaternion();p.location=loc;p.rotation_mode='QUATERNION';p.rotation_quaternion=br@delta;p.scale=sc;ap.append(name)
 bpy.context.view_layer.update();Path(report).write_text(json.dumps({'applied_bones':ap,'bone_count':len(ap),'reference_preserved':True,'structural_layer_preserved':structural(a)['present']},ensure_ascii=False,indent=2),encoding='utf-8');bpy.ops.wm.save_as_mainfile(filepath=blend);export(preview,a)
def import_model(path):
 before=set(bpy.data.objects);ext=path.suffix.lower()
 if ext=='.fbx':bpy.ops.import_scene.fbx(filepath=str(path),use_anim=True)
 elif ext in {'.glb','.gltf'}:bpy.ops.import_scene.gltf(filepath=str(path),import_pack_images=False)
 else:raise RuntimeError('Formato de animação não suportado.')
 return [o for o in bpy.data.objects if o not in before]
def action_for(a):
 if a.animation_data and a.animation_data.action:return a.animation_data.action
 names={b.name for b in a.data.bones};best=None;score=-1
 for act in bpy.data.actions:
  s=0
  try:curves=act.fcurves
  except Exception:continue
  for c in curves:
   m=re.search(r'pose\.bones\["(.+?)"\]',c.data_path)
   if m and m.group(1) in names:s+=1
  if s>score:best,score=act,s
 if best and score>0:a.animation_data_create().action=best;return best
 return None
def restq(b):return (b.parent.matrix_local.inverted()@b.matrix_local if b.parent else b.matrix_local).to_quaternion()
def mapping(src,tgt):
 by={norm(b.name):b.name for b in tgt.data.bones};m={b.name:by[norm(b.name)] for b in src.data.bones if norm(b.name) in by};ss=semmap(src);ts=semmap(tgt)
 for k,sn in ss.items():
  if k in ts:m[sn]=ts[k]
 return m,ss,ts
def hierarchy(src,tgt,m):
 checks=good=0
 for sn,tn in m.items():
  s=src.data.bones.get(sn);t=tgt.data.bones.get(tn)
  if not s or not t or not s.parent or not t.parent or s.parent.name not in m:continue
  checks+=1;good+=m[s.parent.name]==t.parent.name
 return good/checks if checks else 1
def bone_height(a,s):
 h=a.data.bones.get(s.get('hips',''));head=a.data.bones.get(s.get('head',''))
 if h and head:return max((head.head_local-h.head_local).length,1e-6)
 pts=[p for b in a.data.bones for p in (b.head_local,b.tail_local)];return max(max(p.z for p in pts)-min(p.z for p in pts),1e-6) if pts else 1
def mesh_height(a):
 pts=[o.matrix_world@Vector(c) for o in meshes(a) for c in o.bound_box]
 return max(max(p.z for p in pts)-min(p.z for p in pts),1e-6) if pts else bone_height(a,semmap(a))
def finite(m):return all(math.isfinite(float(v)) for row in m for v in row)
def validate(a,action,start,end,h):
 samples=sorted(set(int(round(start+(end-start)*t)) for t in (0,.25,.5,.75,1)));mx=0;bad=0
 for f in samples:
  bpy.context.scene.frame_set(f);bpy.context.view_layer.update();bad+=sum(not finite(p.matrix) for p in a.pose.bones);pts=[];dg=bpy.context.evaluated_depsgraph_get()
  for o in meshes(a):
   ev=o.evaluated_get(dg);pts.extend(ev.matrix_world@Vector(c) for c in ev.bound_box)
  if pts:
   xs=[p.x for p in pts];ys=[p.y for p in pts];zs=[p.z for p in pts];mx=max(mx,max(max(xs)-min(xs),max(ys)-min(ys),max(zs)-min(zs)))
 keyed=set()
 try:curves=action.fcurves
 except Exception:curves=[]
 for c in curves:
  m=re.search(r'pose\.bones\["(.+?)"\]',c.data_path)
  if m:keyed.add(m.group(1))
 s=semmap(a);keys=['left_upper_arm','right_upper_arm','left_forearm','right_forearm','left_thigh','right_thigh','left_shin','right_shin'];cov=sum(s.get(k) in keyed for k in keys)/len(keys);ratio=mx/max(h,1e-6);return {'passed':bad==0 and ratio<4 and cov>=.5,'sampled_frames':samples,'nonfinite_pose_matrices':bad,'max_extent_to_body_height':round(ratio,4),'joint_channel_coverage':round(cov,4)}
def animate(base,anim,blend,preview,report,root_motion):
 bpy.ops.wm.open_mainfile(filepath=base,load_ui=False);tgt=armature();tgt.data.pose_position='POSE';tgt.animation_data_create().action=None;baseh=mesh_height(tgt);basis={p.name:p.matrix_basis.decompose() for p in tgt.pose.bones};struct=structural(tgt);existing=set(bpy.data.objects);imp=import_model(Path(anim));arms=[o for o in imp if o.type=='ARMATURE'] or [o for o in bpy.data.objects if o.type=='ARMATURE' and o not in existing and o!=tgt]
 if not arms:raise RuntimeError('A animação importada não contém armature.')
 src=max(arms,key=lambda a:(bool(action_for(a)),len(a.data.bones)));act=action_for(src)
 if not act:raise RuntimeError('Nenhuma Action utilizável foi encontrada no arquivo de animação.')
 m,ss,ts=mapping(src,tgt);deform=[b for b in tgt.data.bones if b.use_deform];ratio=len(set(m.values()))/max(1,len(deform));core=sum(ss.get(k) in m and m.get(ss.get(k))==ts.get(k) for k in CORE if ss.get(k) and ts.get(k));hr=hierarchy(src,tgt,m);angles=[];corr={}
 for sn,tn in m.items():
  sb=src.data.bones.get(sn);tb=tgt.data.bones.get(tn)
  if not sb or not tb:continue
  qs,qt=restq(sb),restq(tb);angles.append(math.degrees(qs.rotation_difference(qt).angle));corr[sn]=qt@qs.inverted()
 mean=sum(angles)/len(angles) if angles else 180;mx=max(angles) if angles else 180;compat={'mapped_bones':len(m),'target_deform_bones':len(deform),'target_mapping_ratio':round(ratio,4),'core_semantic_matches':int(core),'core_semantic_total':len(CORE),'hierarchy_ratio':round(hr,4),'mean_rest_orientation_delta_degrees':round(mean,3),'max_rest_orientation_delta_degrees':round(mx,3)};block=[];warn=[]
 if core<8:block.append('Poucos ossos corporais essenciais puderam ser mapeados.')
 if ratio<.35:block.append('Cobertura do esqueleto alvo abaixo de 35%.')
 if hr<.55:block.append('A hierarquia mapeada difere demais do esqueleto alvo.')
 if mean>95:block.append('A orientação média da pose de referência é incompatível para retargeting automático.')
 elif mean>25:warn.append('A pose/orientação de referência difere; correção de eixos locais foi aplicada e exige revisão visual.')
 start,end=map(float,act.frame_range);data={'status':'needs_manual_mapping' if block else 'processing','source_armature':src.name,'target_armature':tgt.name,'source_action':act.name,'compatibility':compat,'mapping':m,'root_motion':root_motion,'structural_layer_detected':struct,'blockers':block,'warnings':warn,'retargeting_method':'sampled_local_rotation_delta_with_rest_axis_correction','weight_transfer_performed':False}
 if block:Path(report).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');return
 scale=bone_height(tgt,ts)/bone_height(src,ss);src.animation_data_create().action=act;bpy.context.scene.frame_set(int(round(start)));bpy.context.view_layer.update();srn=ss.get('hips');trn=ts.get('hips');sr=src.pose.bones.get(srn) if srn else None;origin=sr.matrix_basis.to_translation().copy() if sr else Vector((0,0,0));baked=bpy.data.actions.new(name=f'Bodiez_{act.name}_Retargeted');tgt.animation_data_create().action=baked;step=max(1,int(math.ceil(max(1,end-start)/600)));frames=list(range(int(math.floor(start)),int(math.ceil(end))+1,step));last=int(math.ceil(end));frames+=[] if frames[-1]==last else [last]
 for f in frames:
  bpy.context.scene.frame_set(f);bpy.context.view_layer.update()
  for sn,tn in m.items():
   sp=src.pose.bones.get(sn);tp=tgt.pose.bones.get(tn)
   if not sp or not tp or tn not in basis:continue
   loc,br,sc=basis[tn];q=sp.matrix_basis.to_quaternion();c=corr.get(sn);q=c@q@c.inverted() if c else q;tp.location=loc;tp.rotation_mode='QUATERNION';tp.rotation_quaternion=br@q;tp.scale=sc;tp.keyframe_insert(data_path='rotation_quaternion',frame=f,group=tn)
   if sn==srn and tn==trn:
    d=(sp.matrix_basis.to_translation()-origin)*scale
    if root_motion=='in_place':d.x=0;d.y=0
    tp.location=loc+d;tp.keyframe_insert(data_path='location',frame=f,group=tn)
 bpy.context.scene.frame_start=int(math.floor(start));bpy.context.scene.frame_end=int(math.ceil(end));bpy.context.scene.frame_set(bpy.context.scene.frame_start)
 for o in list(imp):
  if o!=tgt and o.name in bpy.data.objects:bpy.data.objects.remove(o,do_unlink=True)
 tgt.animation_data_create().action=baked;bpy.context.view_layer.update();val=validate(tgt,baked,start,end,baseh)
 if not val['passed']:warn.append('A validação geométrica detectou comportamento que precisa de revisão visual.')
 data.update({'status':'ready' if val['passed'] else 'review_required','warnings':warn,'target_scale_from_reference':round(scale,6),'frame_start':start,'frame_end':end,'sample_step':step,'validation':val,'proportion_changes_checked':bool(struct.get('present')),'structural_layer_preserved':True,'root_motion_note':'Preservado no quadril' if root_motion=='preserve' else 'X/Y removidos; movimento vertical preservado'});Path(report).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');bpy.ops.wm.save_as_mainfile(filepath=blend);export(preview,tgt)
def main():
 a=sys.argv[sys.argv.index('--')+1:];cmd=a[0]
 if cmd=='prepare':prep(*a[1:5])
 elif cmd=='pose':pose_apply(*a[1:6])
 elif cmd=='animation':animate(*a[1:7])
 else:raise RuntimeError('Ação interna inválida.')
 print(RESULT_PREFIX+json.dumps({'ok':True,'action':cmd}))
try:main()
except Exception as e:traceback.print_exc();print(RESULT_PREFIX+json.dumps({'ok':False,'error':str(e)}));raise
