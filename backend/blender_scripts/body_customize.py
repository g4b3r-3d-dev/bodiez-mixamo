import bpy,sys,json,re,hashlib
from pathlib import Path
from mathutils import Vector
sys.path.insert(0, str(Path(__file__).resolve().parent))
from breast_morph import MARKER_SOURCE, breast_bones, marker_info, bone_morphs, marker_morphs
from curve_morph import curve_morphs, KEY as CURVE_KEY, VERSION as CURVE_VERSION
from natural_shape import ShapeGuard, apply_guarded
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.body_profile import natural_values

SEM={'head':{'head'},'left_upper_arm':{'leftarm','leftupperarm','upperarml'},'right_upper_arm':{'rightarm','rightupperarm','upperarmr'},'left_forearm':{'leftforearm','leftlowerarm','lowerarml'},'right_forearm':{'rightforearm','rightlowerarm','lowerarmr'},'left_thigh':{'leftupleg','leftthigh','thighl'},'right_thigh':{'rightupleg','rightthigh','thighr'},'left_shin':{'leftleg','leftlowerleg','calfl'},'right_shin':{'rightleg','rightlowerleg','calfr'},'spine':{'spine'},'spine1':{'spine1','spine01'},'spine2':{'spine2','spine02','chest'},'hips':{'hips','pelvis'}}
REGIONS={'arm_volume':['left_upper_arm','right_upper_arm','left_forearm','right_forearm'],'leg_volume':['left_thigh','right_thigh','left_shin','right_shin'],'torso_volume':['hips','spine','spine1','spine2']}
MORPH_VERSION=2
def norm(n):
 n=n.split('|')[-1].rsplit(':',1)[-1];n=re.sub(r'[^A-Za-z0-9]','',n).lower();return n[10:] if n.startswith('mixamorig') else n
def armature():
 arms=[o for o in bpy.context.scene.objects if o.type=='ARMATURE']
 if not arms:raise RuntimeError('Nenhum armature encontrado.')
 def score(a):
  names={norm(b.name) for b in a.data.bones};return sum(bool(names&v) for v in SEM.values())
 return max(arms,key=lambda a:(score(a),len(a.data.bones)))
def matches(a):
 lookup={norm(b.name):b.name for b in a.data.bones};out={}
 for k,variants in SEM.items():
  for v in variants:
   if v in lookup:out[k]=lookup[v];break
 return out
def meshes(a):
 out=[]
 for o in bpy.context.scene.objects:
  if o.type!='MESH':continue
  if any(m.type=='ARMATURE' and m.object==a for m in o.modifiers) or o.parent==a:out.append(o)
 return out
def driven_names(m):
 keys=m.data.shape_keys;out=set();ad=keys.animation_data if keys else None
 for d in (ad.drivers if ad else []):
  x=re.search(r'key_blocks\["(.+?)"\]\.value',d.data_path)
  if x:out.add(x.group(1))
 return out
def existing_sources(ms):
 out=[]
 for m in ms:
  keys=m.data.shape_keys
  if not keys:continue
  driven=driven_names(m)
  for k in keys.key_blocks:
   if k==keys.reference_key or k.name.startswith('Bodiez_Auto_'):continue
   sid='existing:'+hashlib.sha1((m.name+'\0'+k.name).encode()).hexdigest()[:12]
   out.append({'source_id':sid,'type':'existing','display_name':m.name+' / '+k.name,'control_hint':None,'driven':k.name in driven,'slider_min':float(k.slider_min),'slider_max':float(k.slider_max),'targets':[{'mesh':m.name,'key':k.name}]})
 return out
def has_weight(m,b):
 g=m.vertex_groups.get(b)
 if not g:return False
 gi=g.index
 return any(any(x.group==gi and x.weight>.01 for x in v.groups) for v in m.data.vertices)
def closest(point,bone):
 seg=bone.tail_local-bone.head_local
 if seg.length_squared<1e-12:return bone.head_local.copy()
 t=max(0,min(1,(point-bone.head_local).dot(seg)/seg.length_squared));return bone.head_local+seg*t
def auto_morph(m,a,bones,name):
 candidates=[]
 for bn in bones:
  g=m.vertex_groups.get(bn);b=a.data.bones.get(bn)
  if g and b:candidates.append((g.index,b))
 if not candidates:return None
 if not m.data.shape_keys:m.shape_key_add(name='Basis',from_mix=False)
 key=m.data.shape_keys.key_blocks.get(name) or m.shape_key_add(name=name,from_mix=False);key.value=0;key.slider_min=-1;key.slider_max=1
 arm_from_mesh=a.matrix_world.inverted()@m.matrix_world;mesh_dir=m.matrix_world.inverted().to_3x3()@a.matrix_world.to_3x3();affected=0
 # Blend all bones in a region: choosing just one spine bone left most of
 # the chest untouched and max(single weight) weakened blended joints.
 for v in m.data.vertices:
  key.data[v.index].co=m.data.shape_keys.reference_key.data[v.index].co
  weights={x.group:x.weight for x in v.groups}
  p=arm_from_mesh@v.co; displacement=Vector((0,0,0))
  for index,bone in candidates:
   weight=weights.get(index,0)
   if weight>.001:displacement+=(p-closest(p,bone))*weight
  if displacement.length<1e-8:continue
  key.data[v.index].co=v.co+(mesh_dir@displacement)*.65;affected+=1
 if not affected:
  m.shape_key_remove(key)
  return None
 m['bodiez_version_'+name]=MORPH_VERSION
 return {'mesh':m.name,'key':key.name}
def ensure_root():
 root=bpy.data.objects.get('Bodiez_CustomizationRoot') or bpy.data.objects.new('Bodiez_CustomizationRoot',None)
 if not root.users_collection:bpy.context.scene.collection.objects.link(root)
 root.scale=(1,1,1)
 for o in list(bpy.context.scene.objects):
  if o!=root and o.parent is None and o.type not in {'CAMERA','LIGHT'}:
   w=o.matrix_world.copy();o.parent=root;o.matrix_world=w
 return root
def export(path):
 # The body preview must show the current proportions, including pose offsets.
 Path(path).parent.mkdir(parents=True,exist_ok=True);bpy.ops.export_scene.gltf(filepath=path,export_format='GLB',use_selection=False,export_yup=True,export_skins=True,export_morph=True,export_animations=False,export_current_frame=True,export_rest_position_armature=False,export_cameras=False,export_lights=False)
def body_reference(a):
 # Imported FBX actions/NLA otherwise overwrite the sliders on dependency updates.
 # Retain the animation datablocks in this copy and leave source.blend untouched.
 ad=a.animation_data
 if ad:
  if ad.action:
   ad.action.use_fake_user=True
   a['bodiez_source_action']=ad.action.name
   ad.action=None
  ad.use_nla=False
 a.data.pose_position='POSE'
 reset_pose(a)
 bpy.context.view_layer.update()
def prep(inp,blend,preview,report):
 bpy.ops.wm.open_mainfile(filepath=inp,load_ui=False);a=armature();body_reference(a);mm=matches(a);ms=meshes(a)
 if not ms:raise RuntimeError('Nenhuma malha skinnada encontrada.')
 controls={};req={'head_size':['head'],'shoulder_width':['left_upper_arm','right_upper_arm'],'hip_width':['left_thigh','right_thigh'],'arm_length':['left_upper_arm','right_upper_arm','left_forearm','right_forearm'],'leg_length':['left_thigh','right_thigh','left_shin','right_shin']};controls['height']={'enabled':True,'engine':'rig_root_scale'}
 for k,names in req.items():
  ok=all(n in mm and any(has_weight(m,mm[n]) for m in ms) for n in names);controls[k]={'enabled':ok,'engine':'rig_pose_offset','reason':None if ok else 'Ossos/pesos necessários não identificados.'}
 generated=[];defaults={}
 for control,keys in REGIONS.items():
  targets=[];bones=[mm[k] for k in keys if k in mm]
  for m in ms:
   t=auto_morph(m,a,bones,'Bodiez_Auto_'+control)
   if t:targets.append(t)
  controls[control]={'enabled':bool(targets),'engine':'shape_key','generated_assisted':bool(targets),'reason':None if targets else 'Não foi possível gerar morph regional pelos pesos.'}
  if targets:
   sid='auto:'+control;generated.append({'source_id':sid,'type':'generated','display_name':'Morph assistido: '+control,'control_hint':control,'driven':False,'slider_min':-1,'slider_max':1,'targets':targets});defaults[control]=sid
 targets=curve_morphs(a,ms,mm)
 controls['feminine_curves']={'enabled':bool(targets),'engine':'shape_key','generated_assisted':bool(targets),'reason':None if targets else 'Ossos e pesos do tronco e quadris necessários não identificados.'}
 if targets:
  generated.append({'source_id':'auto:feminine_curves','type':'generated','display_name':'Cintura, quadris e glúteos','control_hint':'feminine_curves','driven':False,'slider_min':0,'slider_max':1,'targets':targets});defaults['feminine_curves']='auto:feminine_curves'
 existing=existing_sources(ms);bones=breast_bones(a,ms);targets=bone_morphs(a,ms,bones) if bones else []
 if targets:
  generated.append({'source_id':'auto:breast_size','type':'generated','display_name':'Seios pelos ossos','control_hint':'breast_size','driven':False,'slider_min':-.5,'slider_max':1,'targets':targets});defaults['breast_size']='auto:breast_size'
 generated.append({'source_id':MARKER_SOURCE,'type':'markers','display_name':'Seios pelos marcadores','control_hint':'breast_size','driven':False,'slider_min':-.5,'slider_max':1,'targets':[]})
 controls['breast_size']={'enabled':bool(targets),'engine':'shape_key','generated_assisted':bool(targets),'requires_markers':not bool(targets),'bones':bones,'reason':None if targets else 'Ossos dos seios não identificados. Posicione dois marcadores ou selecione um shape key existente.'}
 data={'armature':a.name,'semantic_matches':mm,'controls':controls,'morph_sources':generated+existing,'default_bindings':defaults,'breast_marker_info':marker_info(a,ms,mm),'structural_method':{'name':'non_destructive_pose_offset_layer','description':'Mudanças estruturais usam escala raiz e transforms de pose; rest pose não é reescrita.'},'preservation':{'topology_changed':False,'destructive_modifiers_applied':False,'existing_shape_keys_removed':False},'limitations':['Morphs assistidos derivam dos pesos ou marcadores e não substituem morphs artísticos/anatômicos.','A área dos marcadores também deforma roupas que cobrem os seios. Ajuste o raio e confira de frente e de lado.','A camada estrutural deverá ser conciliada com animações na Etapa 5.']}
 Path(report).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');bpy.ops.wm.save_as_mainfile(filepath=blend);export(preview)
def reset_pose(a):
 for p in a.pose.bones:p.matrix_basis.identity()
def width(a,mm,l,r,f):
 if l not in mm or r not in mm or abs(f-1)<1e-8:return
 connected=[mm[key] for key in (l,r) if a.data.bones[mm[key]].use_connect]
 if connected:
  # Connected bones ignore pose translations. Unlock only in the revision copy;
  # keep parents and rest matrices intact, and record which flags changed.
  bpy.context.view_layer.objects.active=a
  bpy.ops.object.mode_set(mode='EDIT')
  for name in connected:a.data.edit_bones[name].use_connect=False
  bpy.ops.object.mode_set(mode='OBJECT')
  a['bodiez_width_offset_bones']=list(a.get('bodiez_width_offset_bones',[]))+connected
 left=a.data.bones[mm[l]];right=a.data.bones[mm[r]]
 delta=(left.head_local-right.head_local)*(.5*(f-1))
 for bone,offset in ((left,delta),(right,-delta)):
  a.pose.bones[bone.name].location+=bone.matrix_local.to_3x3().inverted()@offset
def chain(a,mm,names,f):
 for n in names:
  if n in mm:a.pose.bones[mm[n]].scale.y*=f
def apply(inp,request,blend,preview,report):
 bpy.ops.wm.open_mainfile(filepath=inp,load_ui=False);q=json.loads(Path(request).read_text());v=q['values'];resolved=q.get('resolved',{});a=armature();body_reference(a);mm=matches(a)
 marker_result=None
 curve_targets=resolved.get('feminine_curves',[])
 if any(t['key']==CURVE_KEY and (m:=bpy.data.objects.get(t['mesh'])) is not None and m.get('bodiez_version_'+CURVE_KEY)!=CURVE_VERSION for t in curve_targets):
  curve_morphs(a,meshes(a),mm)
 if q.get('bindings',{}).get('breast_size')==MARKER_SOURCE:
  ms=meshes(a);targets,affected=marker_morphs(ms,q['breast_markers'],marker_info(a,ms,mm));resolved['breast_size']=targets;marker_result={'markers':q['breast_markers'],'affected_vertices_per_side':affected}
 # Regenerate any legacy morphs before measuring the untouched baseline.
 for control,targets in resolved.items():
  for t in targets:
   m=bpy.data.objects.get(t['mesh'])
   if m and control in REGIONS and t['key']=='Bodiez_Auto_'+control and m.get('bodiez_version_'+t['key'])!=MORPH_VERSION:
    auto_morph(m,a,[mm[n] for n in REGIONS[control] if n in mm],t['key'])
 root=ensure_root();bpy.context.view_layer.update();guard=ShapeGuard(meshes(a),a,mm);applied={}
 def apply_values(values):
  reset_pose(a)
  h=float(values.get('height',1));root.scale=(h,h,h)
  if 'head' in mm:
   f=float(values.get('head_size',1));a.pose.bones[mm['head']].scale=(f,f,f)
  width(a,mm,'left_upper_arm','right_upper_arm',float(values.get('shoulder_width',1)))
  width(a,mm,'left_thigh','right_thigh',float(values.get('hip_width',1)))
  chain(a,mm,['left_upper_arm','right_upper_arm','left_forearm','right_forearm'],float(values.get('arm_length',1)))
  chain(a,mm,['left_thigh','right_thigh','left_shin','right_shin'],float(values.get('leg_length',1)))
  for control,targets in resolved.items():
   applied[control]=[]
   for t in targets:
    m=bpy.data.objects.get(t['mesh'])
    k=m.data.shape_keys.key_blocks.get(t['key']) if m and m.data.shape_keys else None
    if k:k.value=float(values.get(control,0));applied[control].append(t)
 requested=q.get('requested_values',v)
 v,natural_report=apply_guarded(natural_values(v),apply_values,guard)
 natural_report['adjustments']={k:{'requested':requested.get(k,value),'applied':value} for k,value in v.items() if abs(requested.get(k,value)-value)>1e-8}
 result={'values':v,'natural_shape':natural_report,'structural':{'method':'non_destructive_pose_offset_layer','values':{k:v.get(k,1) for k in ('height','head_size','shoulder_width','hip_width','arm_length','leg_length')}},'morphs':{'method':'shape_keys','applied':applied},'breast_markers':marker_result,'double_deformation_avoided':True}
 Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');bpy.ops.wm.save_as_mainfile(filepath=blend);export(preview)

def main():
 a=sys.argv[sys.argv.index('--')+1:]
 if a[0]=='prepare':prep(*a[1:5])
 elif a[0]=='apply':apply(*a[1:6])
 else:raise RuntimeError('Ação inválida.')
 print('BODIEZ_RESULT:'+json.dumps({'ok':True,'action':a[0]}))
if __name__=='__main__':
 try:main()
 except Exception as e:
  import traceback;traceback.print_exc();print('BODIEZ_RESULT:'+json.dumps({'ok':False,'error':str(e)}));raise
