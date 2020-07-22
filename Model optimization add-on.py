#АЛГОРИТМ
#
#получить список файлов obj и fbx из папки
#если такие файлы есть, то создаём новую папку ("optimized models") внутри указанной папки
#
#в цикле по списку моделей obj fbx:
#	очиcтить сцену blender
#	открыть модель в blender
#	применить к ней скрипты:
#		если ползунок decimate < 1.0, то упрощаем модель
#		если есть галочка на del inner geom, то удаляем внутреннюю геометрию
#	экспортировать модель в новую папку ("optimized models")

bl_info = {
    "name": "Optimization Addon",
    "blender": (2, 80, 0),
    "category": "Object",
}

import bpy
from bpy.types import (
    AddonPreferences,
    Operator,
    Panel,
    PropertyGroup,
)
import os, bmesh, time

#Убирает все предыдущие итерации Decimate с модели
def cleanAllDecimateModifiers(obj):
	for m in obj.modifiers:
		if(m.type=="DECIMATE"):
			obj.modifiers.remove(modifier=m)

def decimate(decimateRatio):
	modifierName='DecimateMod'
	#для всех обнаруженных деталей модели убираем предыдущие итерации модификатора Decimate и применяем новую
	for obj in bpy.data.objects:
		if(obj.type=="MESH"):
			cleanAllDecimateModifiers(obj)
			modifier=obj.modifiers.new(modifierName,'DECIMATE')
			modifier.ratio=decimateRatio
			modifier.use_collapse_triangulate=True
	return True

def delInnerGeom(secondsToDeleteInnerGeometry):
	# засекаем время выполнения скрипта
	start_time = time.time()
	
	# получить лист исходных моделей
	bpy.ops.object.select_by_type(type='MESH')
	mesh_origins = tuple(bpy.context.selected_objects)

	# проверка если количество исходников меньше 2
	if len(mesh_origins) < 2:
		print('There should be at least 2 MESH objects.')
		return False

	# получить лист BMesh из исходных моделей
	bm_list = list()
	for i in range(len(mesh_origins)):
		bm_list.append(bmesh.new()) # create an empty BMesh
		bm_list[i].from_object(mesh_origins[i], bpy.context.evaluated_depsgraph_get(), deform=True, cage=False, face_normals=True) # fill it in from a Mesh

	# создать лист множеств bm_verts
	bm_verts = [set() for i in range(len(mesh_origins))]
	for i in range(len(bm_list)):
		for v in bm_list[i].verts:
			bm_verts[i].add((v.co.x, v.co.y, v.co.z))
	bm_verts = tuple(bm_verts)
				
	# создать лист множеств to_delete_verts
	to_delete_verts = [set() for i in range(len(mesh_origins))]
		
	# развесить всем исходникам модификатор boolean intersect
	mods_list = list()
	for i in range(len(mesh_origins)):
		mods_list.append(mesh_origins[i].modifiers.new(type='BOOLEAN', name='bool intersect'))
		mods_list[i].operation = 'INTERSECT'
			
	def get_to_del_verts(a, b):
		# исходнику a в boolean добавляем исходник b
		mods_list[a].object = mesh_origins[b]
		mods_list[b].object = None
			
		# берём BMesh из полученного a, назовём inner_geom
		inner_geom = bmesh.new()
		inner_geom.from_object(mesh_origins[a], bpy.context.evaluated_depsgraph_get(), deform=True, cage=False, face_normals=True)
			
		# создаём множество same_verts
		same_verts = set()
			
		# в цикле по вершинам inner_geom сравниваем координаты с вершинами из BMesh
		for v in inner_geom.verts:
			if (v.co.x, v.co.y, v.co.z) in bm_verts[a]:
				# если такая вершина есть, то добавляем её в same_verts
				same_verts.add((v.co.x, v.co.y, v.co.z))
					
		# same_verts добавляем в to_delete_verts[a]
		to_delete_verts[a] = to_delete_verts[a].union(same_verts)
			
		# исходнику a в boolean убираем объект b
		mods_list[a].object = None
	
	# если функция выполнилась за определённое время, возвращает True
	def funcExecutedOnTime(get_to_del_verts):
		# цикл проходит попарно по всем мешам
		for i in range(len(mesh_origins)-1):
			for k in range(i+1, len(mesh_origins)):
				get_to_del_verts(i, k)
				get_to_del_verts(k, i)
				if secondsToDeleteInnerGeometry > 0 and time.time() - start_time > secondsToDeleteInnerGeometry:
					return False
		return True
	
	if funcExecutedOnTime(get_to_del_verts):
		to_delete_verts = tuple(to_delete_verts)
		
		# в цикле по BMesh удаляем невидимые трисы
		for i in range(len(bm_list)):
			bm_list[i].select_mode = {'VERT', 'EDGE', 'FACE'}
			for f in bm_list[i].faces:
				f.select = False
			for e in bm_list[i].edges:
				e.select = False
			for v in bm_list[i].verts:
				if (v.co.x, v.co.y, v.co.z) in to_delete_verts[i]:
					v.select = True
				else:
					v.select = False
				
			# выделяем все трисы, у которых вершины невидимые
			bm_list[i].select_flush_mode()
			faces = [f for f in bm_list[i].faces if f.select]
			
			# удаляем невидимые трисы
			bmesh.ops.delete(bm_list[i], geom=faces, context='FACES')
			
		# убрать все модификаторы boolean
		for obj in mesh_origins:
			for m in obj.modifiers:
				if(m.type=='BOOLEAN'):
					obj.modifiers.remove(modifier=m)
			
		# применить все BMesh к исходникам
		for i in range(len(mesh_origins)):
			bm_list[i].to_mesh(mesh_origins[i].data)
		
		# освободить все BMesh
		for i in range(len(bm_list)):
			bm_list[i].free()
		
		for obj in bpy.data.objects:
			if(obj.type=="MESH"):
				cleanAllDecimateModifiers(obj)
		
		return True
	else:
		# убрать все модификаторы boolean
		for obj in mesh_origins:
			for m in obj.modifiers:
				if(m.type=='BOOLEAN'):
					obj.modifiers.remove(modifier=m)
		
		# освободить все BMesh
		for i in range(len(bm_list)):
			bm_list[i].free()
		return False
	
class Optimize(Operator):
	bl_label = "Optimize"
	bl_idname = "object.optimize"
	bl_description = "Optimize models"
	bl_space_type = "VIEW_3D"
	bl_region_type = "UI"
	bl_options = {'REGISTER', 'UNDO'}
	
	modelsDirectory: bpy.props.StringProperty(name="Models directory")
	##пользователь выбирает степень оптимизации модели
	decimateRatio: bpy.props.FloatProperty(name="Ratio", default=0.4, min=0, max=1)
	deleteInnerGeometry: bpy.props.BoolProperty(name="Delete inner geometry", default=False)
	secondsToDeleteInnerGeometry: bpy.props.IntProperty(name="Seconds to del inner geometry", default=0, min=0)
	runScript: bpy.props.BoolProperty(name="RUN SCRIPT", default=False)
	
	def execute(self, context):
		if self.runScript:
			#получить список файлов obj и fbx из папки
			files_list = os.listdir(self.modelsDirectory)
			models_list = list()
			lower_names_list = list()
			for file_name in files_list:
				lower_name = file_name.lower()
				if lower_name.endswith(('.obj', '.fbx')):
					models_list.append(file_name)
					lower_names_list.append(lower_name)
			
			#если такие файлы есть, то создаём новую папку ("optimized models") внутри указанной папки
			if len(models_list) > 0:
				path = self.modelsDirectory + '\\optimized models'
				if not os.path.exists(path):
					os.mkdir(path)
					
				#в цикле по списку моделей obj fbx:
				for i in range(len(models_list)):
					#очистить сцену blender
					bpy.ops.object.select_all(action='SELECT')
					bpy.ops.object.delete()
					
					#открыть модель в blender
					if lower_names_list[i].endswith('.obj'):
						bpy.ops.import_scene.obj(filepath=self.modelsDirectory+'\\'+models_list[i])
					elif lower_names_list[i].endswith('.fbx'):
						bpy.ops.import_scene.fbx(filepath=self.modelsDirectory+'\\'+models_list[i])
					
					#применить к модели скрипты
					#если ползунок decimate < 1.0 то упрощаем
					if self.decimateRatio < 1.0:
						decimate(self.decimateRatio)
					
					#если есть галочка на del inner geom, то удаляем внутреннюю геометрию
					if self.deleteInnerGeometry:
						delInnerGeom(self.secondsToDeleteInnerGeometry)
						
					#экспортировать модель в новую папку ("optimized models")
					if lower_names_list[i].endswith('.obj'):
						bpy.ops.export_scene.obj(filepath=path+'\\'+models_list[i], check_existing=False)
					elif lower_names_list[i].endswith('.fbx'):
						bpy.ops.export_scene.fbx(filepath=path+'\\'+models_list[i], check_existing=False)
			self.runScript = False
		return {'FINISHED'}

def menu_func(self, context):
	self.layout.operator(Optimize.bl_idname)

##регистрация аддона и дерегистрация после выполнения    
def register():
	bpy.utils.register_class(Optimize)
	bpy.types.VIEW3D_MT_object.append(menu_func)

def unregister():
	bpy.utils.unregister_class(Optimize)
	bpy.types.VIEW3D_MT_object.remove(menu_func)
##if name необязательно, но позволяет запускать аддон прямо из текстового редактора Blender
if __name__ == "__main__":
	register()
