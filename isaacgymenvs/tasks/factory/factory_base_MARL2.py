# Copyright (c) 2021-2022, NVIDIA Corporation
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

"""Factory: base class.

Inherits Gym's VecTask class and abstract base class. Inherited by environment classes. Not directly executed.

Configuration defined in FactoryBase_MARL2.yaml. Asset info defined in factory_asset_info_franka_table.yaml.
"""


import hydra
import math
import numpy as np
import os
import sys
import torch

from gym import logger
from isaacgym import gymapi, gymtorch, torch_utils
from isaacgymenvs.tasks.base.vec_task import VecTask
import isaacgymenvs.tasks.factory.factory_control_MARL2 as fc
from isaacgymenvs.tasks.factory.factory_schema_class_base import FactoryABCBase
from isaacgymenvs.tasks.factory.factory_schema_config_base import FactorySchemaConfigBase


class FactoryBase_MARL2(VecTask, FactoryABCBase):

    def __init__(self, cfg, rl_device, sim_device, graphics_device_id, headless, virtual_screen_capture, force_render):
        """Initialize instance variables. Initialize VecTask superclass."""

        self.cfg = cfg
        self.cfg['headless'] = headless

        self._get_base_yaml_params()

        if self.cfg_base.mode.export_scene:
            sim_device = 'cpu'

        super().__init__(cfg, rl_device, sim_device, graphics_device_id, headless, virtual_screen_capture, force_render)  # create_sim() is called here

    def _get_base_yaml_params(self):
        """Initialize instance variables from YAML files."""

        cs = hydra.core.config_store.ConfigStore.instance()
        cs.store(name='factory_schema_config_base', node=FactorySchemaConfigBase)

        config_path = 'task/FactoryBase_MARL2.yaml'  # relative to Gym's Hydra search path (cfg dir)
        self.cfg_base = hydra.compose(config_name=config_path)
        self.cfg_base = self.cfg_base['task']  # strip superfluous nesting

        asset_info_path = '../../assets/factory/yaml/factory_asset_info_franka_table.yaml'  # relative to Gym's Hydra search path (cfg dir)
        self.asset_info_franka_table = hydra.compose(config_name=asset_info_path)
        self.asset_info_franka_table = self.asset_info_franka_table['']['']['']['']['']['']['assets']['factory']['yaml']  # strip superfluous nesting


    def create_sim(self):
        """Set sim and PhysX params. Create sim object, ground plane, and envs."""

        if self.cfg_base.mode.export_scene:
            self.sim_params.use_gpu_pipeline = False

        self.sim = super().create_sim(compute_device=self.device_id,
                                      graphics_device=self.graphics_device_id,
                                      physics_engine=self.physics_engine,
                                      sim_params=self.sim_params)
        self._create_ground_plane()
        self.create_envs()  # defined in subclass

    def _create_ground_plane(self):
        """Set ground plane params. Add plane."""

        plane_params = gymapi.PlaneParams()
        plane_params.normal = gymapi.Vec3(0.0, 0.0, 1.0)
        plane_params.distance = 0.0  # default = 0.0
        plane_params.static_friction = 1.0  # default = 1.0
        plane_params.dynamic_friction = 1.0  # default = 1.0
        plane_params.restitution = 0.0  # default = 0.0

        self.gym.add_ground(self.sim, plane_params)

    def import_franka_assets(self):
        """Set Franka and table asset options. Import assets.
           Franka_1 and Franka_2 will have the same asset.
        """

        urdf_root = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'assets', 'factory', 'urdf')
        franka_file = 'factory_franka.urdf'

        franka_options = gymapi.AssetOptions()
        franka_options.flip_visual_attachments = True
        franka_options.fix_base_link = True
        franka_options.collapse_fixed_joints = False
        franka_options.thickness = 0.0  # default = 0.02
        franka_options.density = 1000.0  # default = 1000.0
        franka_options.armature = 0.01  # default = 0.0
        franka_options.use_physx_armature = True
        if self.cfg_base.sim.add_damping:
            franka_options.linear_damping = 1.0  # default = 0.0; increased to improve stability
            franka_options.max_linear_velocity = 1.0  # default = 1000.0; reduced to prevent CUDA errors
            franka_options.angular_damping = 5.0  # default = 0.5; increased to improve stability
            franka_options.max_angular_velocity = 2 * math.pi  # default = 64.0; reduced to prevent CUDA errors
        else:
            franka_options.linear_damping = 0.0  # default = 0.0
            franka_options.max_linear_velocity = 1000.0  # default = 1000.0
            franka_options.angular_damping = 0.5  # default = 0.5
            franka_options.max_angular_velocity = 64.0  # default = 64.0
        franka_options.disable_gravity = True
        franka_options.enable_gyroscopic_forces = True
        franka_options.default_dof_drive_mode = gymapi.DOF_MODE_NONE
        franka_options.use_mesh_materials = True
        if self.cfg_base.mode.export_scene:
            franka_options.mesh_normal_mode = gymapi.COMPUTE_PER_FACE

        table_options = gymapi.AssetOptions()
        table_options.flip_visual_attachments = False  # default = False
        table_options.fix_base_link = True
        table_options.thickness = 0.0  # default = 0.02
        table_options.density = 1000.0  # default = 1000.0
        table_options.armature = 0.0  # default = 0.0
        table_options.use_physx_armature = True
        table_options.linear_damping = 0.0  # default = 0.0
        table_options.max_linear_velocity = 1000.0  # default = 1000.0
        table_options.angular_damping = 0.0  # default = 0.5
        table_options.max_angular_velocity = 64.0  # default = 64.0
        table_options.disable_gravity = False
        table_options.enable_gyroscopic_forces = True
        table_options.default_dof_drive_mode = gymapi.DOF_MODE_NONE
        table_options.use_mesh_materials = False
        if self.cfg_base.mode.export_scene:
            table_options.mesh_normal_mode = gymapi.COMPUTE_PER_FACE

        franka_asset = self.gym.load_asset(self.sim, urdf_root, franka_file, franka_options)
        # table_asset = self.gym.create_box(self.sim, self.asset_info_franka_table.table_depth,
        #                                   self.asset_info_franka_table.table_width, self.cfg_base.env.table_height,
        #                                   table_options)
        # NOTE: changed table width from 1.0 to 4.0 to fit two frankas
        table_asset = self.gym.create_box(self.sim, self.asset_info_franka_table.table_depth,
                                            4.0, self.cfg_base.env.table_height,
                                            table_options)

        return franka_asset, table_asset

    def acquire_base_tensors(self):
        """Acquire and wrap tensors. Create views."""

        """
        Single Agent:
        num_envs:  128                          
        num_actors:  4
        num_bodies:  15
        num_dofs:  9
        _root_state:  (512, 13)
        _body_state:  (1920, 13)
        _dof_state:  (1152, 2)
        _contact_state:  (1920, 3)
        _jacobian:  (128, 11, 6, 9)
        _mass_matrix:  (128, 9, 9)  

        Multi-Agent:
        num_envs:  128
        num_actors:  5
        num_bodies:  27                 # 27-15 = 12. One franka has 12 bodies????????
        num_dofs:  18                   # Double Degree of Freedom
        _root_state:  (640, 13)
        _body_state:  (3456, 13)
        _dof_state:  (2304, 2)
        _contact_state:  (3456, 3)
        _jacobian:  (128, 11, 6, 9)
        _mass_matrix:  (128, 9, 9)
        _jacobian_2:  (128, 11, 6, 9)   # franka_2 jacobian and mass matrix same dimentions as franka_1
        _mass_matrix_2:  (128, 9, 9)
        """

        _root_state = self.gym.acquire_actor_root_state_tensor(self.sim)  # shape = (num_envs * num_actors, 13)
        _body_state = self.gym.acquire_rigid_body_state_tensor(self.sim)  # shape = (num_envs * num_bodies, 13)
        _dof_state = self.gym.acquire_dof_state_tensor(self.sim)  # shape = (num_envs * num_dofs, 2)
        _dof_force = self.gym.acquire_dof_force_tensor(self.sim)  # shape = (num_envs * num_dofs, 1)
        _contact_force = self.gym.acquire_net_contact_force_tensor(self.sim)  # shape = (num_envs * num_bodies, 3)
        _jacobian = self.gym.acquire_jacobian_tensor(self.sim, 'franka')  # shape = (num envs, num_bodies, 6, num_dofs)
        _mass_matrix = self.gym.acquire_mass_matrix_tensor(self.sim, 'franka')  # shape = (num_envs, num_dofs, num_dofs)
        # NOTE: jacobian and mass matrix for franka_2
        _jacobian_2 = self.gym.acquire_jacobian_tensor(self.sim, 'franka_2')  # shape = (num envs, num_bodies, 6, num_dofs)
        _mass_matrix_2 = self.gym.acquire_mass_matrix_tensor(self.sim, 'franka_2')  # shape = (num_envs, num_dofs, num_dofs)
        
        # _mass_matrix = np.concatenate((_mass_matrix, _mass_matrix_2), axis=1)
        # concatenated_matrix = np.concatenate((_jacobian, _jacobian_2), axis=3)
        # _jacobian = np.concatenate((concatenated_matrix, concatenated_matrix), axis=1)


        print("num_envs: ", self.num_envs)
        print("num_actors: ", self.num_actors)
        print("num_bodies: ", self.num_bodies)
        print("num_dofs: ", self.num_dofs)
        print("_root_state: ", _root_state.shape)
        print("_body_state: ", _body_state.shape)
        print("_dof_state: ", _dof_state.shape)
        print("_contact_state: ", _contact_force.shape)
        print("_jacobian: ", _jacobian.shape)
        print("_mass_matrix: ", _mass_matrix.shape)
        print("_jacobian_2: ", _jacobian_2.shape)
        print("_mass_matrix_2: ", _mass_matrix_2.shape)

        self.root_state = gymtorch.wrap_tensor(_root_state)
        self.body_state = gymtorch.wrap_tensor(_body_state)
        self.dof_state = gymtorch.wrap_tensor(_dof_state)
        self.dof_force = gymtorch.wrap_tensor(_dof_force)
        self.contact_force = gymtorch.wrap_tensor(_contact_force)
        self.jacobian = gymtorch.wrap_tensor(_jacobian)
        self.mass_matrix = gymtorch.wrap_tensor(_mass_matrix)
        # NOTE: wrapping tensors for franka_2
        self.jacobian_2 = gymtorch.wrap_tensor(_jacobian_2)
        self.mass_matrix_2 = gymtorch.wrap_tensor(_mass_matrix_2)

        # TODO: concat jacobian and mass matrix
        """
        Jacobian and Mass Matrices
        Shape of Mass Matrix: (num_dofs, num_dofs)
        Franka has 9 DOFS, two Frankas should have 18 DOFS

        Shape of Jacobian Matrix: (num_envs, num_links, 6, num_dofs)
        Franka has 11 links.

        Original Jacobian and Mass Matrices:        
        _jacobian:  (128, 11, 6, 9)  # (num_envs, num_links, 6, num_dofs)
        _mass_matrix:  (128, 9, 9)  # (num_envs, num_dofs, num_dofs)
        _jacobian_2:  (128, 11, 6, 9)
        _mass_matrix_2:  (128, 9, 9)

        Modified Jacobian and Mass Matrices:
        self.jacobian:  torch.Size([128, 22, 6, 18])
        self.mass_matrix:  torch.Size([128, 18, 9])
        """

        # Concat Mass_Matrix
        mass_matrix_cpu = self.mass_matrix.cpu().numpy()
        mass_matrix_2_cpu = self.mass_matrix_2.cpu().numpy()

        self.mass_matrix = np.concatenate((mass_matrix_cpu, mass_matrix_2_cpu), axis=1)
        self.mass_matrix = torch.from_numpy(self.mass_matrix).to(self.root_state.device)

        # Concat Jacobian
        jacobian_cpu = self.jacobian.cpu().numpy()
        jacobian_2_cpu = self.jacobian_2.cpu().numpy()

        concatenated_matrix = np.concatenate((jacobian_cpu, jacobian_2_cpu), axis=3)
        self.jacobian = np.concatenate((concatenated_matrix, concatenated_matrix), axis=1)
        self.jacobian = torch.from_numpy(self.jacobian).to(self.root_state.device)
        
        print("self.root_state: ", self.root_state.shape)
        print("self.body_state: ", self.body_state.shape)
        print("self.dof_state: ", self.dof_state.shape)
        print("self.dof_force: ", self.dof_force.shape)
        print("self.contact_force: ", self.contact_force.shape)
        print("self.jacobian: ", self.jacobian.shape)
        print("self.mass_matrix: ", self.mass_matrix.shape)

        """
        self.root_state:  torch.Size([640, 13])
        self.body_state:  torch.Size([3456, 13])
        self.dof_state:  torch.Size([2304, 2])
        self.dof_force:  torch.Size([2304])
        self.contact_force:  torch.Size([3456, 3])
        self.jacobian:  torch.Size([128, 22, 6, 18])
        self.mass_matrix:  torch.Size([128, 18, 9])
        """
        

        """
        root_positions = root_tensor[:, 0:3]
        root_orientations = root_tensor[:, 3:7]
        root_linvels = root_tensor[:, 7:10]
        root_angvels = root_tensor[:, 10:13]
        """

        """
        self.root_state.view(self.num_envs, self.num_actors, 13) reshapes root_state.
        reshapes the original 2D tensor of size torch.Size([640, 13]) into a new 3D tensor of size torch.Size([128, 5, 13]).

        Specifically, it divides the first dimension of the original tensor (640) into two new dimensions of size 128 and 5, respectively. 
        The resulting tensor has 128 arrays of 5 rows and 13 columns each, in which each row represents an actor.

        128 environments
        5 actors
        self.root_pos has shape [128,5,3]
        """

        self.root_pos = self.root_state.view(self.num_envs, self.num_actors, 13)[..., 0:3]
        self.root_quat = self.root_state.view(self.num_envs, self.num_actors, 13)[..., 3:7]
        self.root_linvel = self.root_state.view(self.num_envs, self.num_actors, 13)[..., 7:10]
        self.root_angvel = self.root_state.view(self.num_envs, self.num_actors, 13)[..., 10:13]
        
        """
        num_envs = 128
        num_bodies = 27
        self.body_state has size (3456, 13) = (num_envs * num_bodies, 13)
        self.body_state.view(self.num_envs, self.num_bodies, 13) reshapes
        changes array from (3456, 13) to (128,27,13). 128 arrays of 27 rows and 13 columns each, in which each row represents a body.
        """

        self.body_pos = self.body_state.view(self.num_envs, self.num_bodies, 13)[..., 0:3]
        self.body_quat = self.body_state.view(self.num_envs, self.num_bodies, 13)[..., 3:7]
        self.body_linvel = self.body_state.view(self.num_envs, self.num_bodies, 13)[..., 7:10]
        self.body_angvel = self.body_state.view(self.num_envs, self.num_bodies, 13)[..., 10:13]

        """
        num_envs = 128
        num_dofs = 18
        _dof_state:  (1152, 2) # shape = (num_envs * num_dofs, 2)
        self.dof_state.view(self.num_envs, self.num_dofs, 2) reshapes
        changes array from (1152, 2) to (128, 18, 2), 128 arrays of 18 rows and 2 columns, in which each row is a dof (of panda robot)

        position is the first column, velocity is the second column
        """

        self.dof_pos = self.dof_state.view(self.num_envs, self.num_dofs, 2)[..., 0]
        self.dof_vel = self.dof_state.view(self.num_envs, self.num_dofs, 2)[..., 1]

        self.dof_force_view = self.dof_force.view(self.num_envs, self.num_dofs, 1)[..., 0]
        self.contact_force = self.contact_force.view(self.num_envs, self.num_bodies, 3)[..., 0:3]
        
        """
        self.dof_pos: torch.Size([128, 18])
        self.mass_matrix:  torch.Size([128, 18, 9])

        """

        self.arm_dof_pos = self.dof_pos[:, 0:7] # NOTE: index 0-7 are the arm positions for franka_1, the others are gripper positions
        self.arm_dof_pos_2 = self.dof_pos[:,9:16]  # NOTE: index 7-14 are the arm positions for franka_2, the others are gripper positions
        self.arm_mass_matrix = self.mass_matrix[:, 0:7, 0:7]  # for Franka arm (not gripper)
        self.arm_mass_matrix_2 = self.mass_matrix[:, 9:16, 0:7]  # for Franka_2 arm (not gripper)

        print("self.body_pos: ", self.body_pos.shape)
        print("self.arm_quat: ", self.body_quat.shape)
        print("self.body_linvel: ", self.body_linvel.shape)
        print("self.body_angvel: ", self.body_angvel.shape)
        print("self.jacobian: ", self.jacobian.shape)

        """
        num_envs = 128
        num_bodies = 27

        self.body_pos:  torch.Size([128, 27, 3])
        self.arm_quat:  torch.Size([128, 27, 4])
        self.body_linvel:  torch.Size([128, 27, 3])
        self.body_angvel:  torch.Size([128, 27, 3])
        self.jacobian:  torch.Size([128, 22, 6, 18])

        self.hand_body_id_env = 8
        self.hand_body_id_env_2 = 20
        self.left_finger_body_id_env = 9
        self.left_finger_body_id_env_2 = 21

        """
        # Franka_1
        self.hand_pos = self.body_pos[:, self.hand_body_id_env, 0:3]
        self.hand_quat = self.body_quat[:, self.hand_body_id_env, 0:4]
        self.hand_linvel = self.body_linvel[:, self.hand_body_id_env, 0:3]
        self.hand_angvel = self.body_angvel[:, self.hand_body_id_env, 0:3]
        self.hand_jacobian = self.jacobian[:, self.hand_body_id_env - 1, 0:6, 0:7]  # minus 1 because base is fixed

        # NOTE: franka_2 Body States
        self.hand_pos_2 = self.body_pos[:, self.hand_body_id_env_2, 0:3]
        self.hand_quat_2 = self.body_quat[:, self.hand_body_id_env_2, 0:4]
        self.hand_linvel_2 = self.body_linvel[:, self.hand_body_id_env_2, 0:3]
        self.hand_angvel_2 = self.body_angvel[:, self.hand_body_id_env_2, 0:3]
        self.hand_jacobian_2 = self.jacobian[:, self.hand_body_id_env_2 - 2, 0:6, 9:16]  # minus 1 because base is fixed

        # Franka_1
        self.left_finger_pos = self.body_pos[:, self.left_finger_body_id_env, 0:3]
        self.left_finger_quat = self.body_quat[:, self.left_finger_body_id_env, 0:4]
        self.left_finger_linvel = self.body_linvel[:, self.left_finger_body_id_env, 0:3]
        self.left_finger_angvel = self.body_angvel[:, self.left_finger_body_id_env, 0:3]
        self.left_finger_jacobian = self.jacobian[:, self.left_finger_body_id_env - 1, 0:6, 0:7]  # minus 1 because base is fixed

        # NOTE: franka_2 Left Finger
        self.left_finger_pos_2 = self.body_pos[:, self.left_finger_body_id_env_2, 0:3]
        self.left_finger_quat_2 = self.body_quat[:, self.left_finger_body_id_env_2, 0:4]
        self.left_finger_linvel_2 = self.body_linvel[:, self.left_finger_body_id_env_2, 0:3]
        self.left_finger_angvel_2 = self.body_angvel[:, self.left_finger_body_id_env_2, 0:3]
        self.left_finger_jacobian_2 = self.jacobian[:, self.left_finger_body_id_env_2 - 2, 0:6, 9:16]  # minus 1 because base is fixed

        # Franka_1
        self.right_finger_pos = self.body_pos[:, self.right_finger_body_id_env, 0:3]
        self.right_finger_quat = self.body_quat[:, self.right_finger_body_id_env, 0:4]
        self.right_finger_linvel = self.body_linvel[:, self.right_finger_body_id_env, 0:3]
        self.right_finger_angvel = self.body_angvel[:, self.right_finger_body_id_env, 0:3]
        self.right_finger_jacobian = self.jacobian[:, self.right_finger_body_id_env - 1, 0:6, 0:7]  # minus 1 because base is fixed

        # NOTE: franka_2 Right Finger
        self.right_finger_pos_2 = self.body_pos[:, self.right_finger_body_id_env_2, 0:3]
        self.right_finger_quat_2 = self.body_quat[:, self.right_finger_body_id_env_2, 0:4]
        self.right_finger_linvel_2 = self.body_linvel[:, self.right_finger_body_id_env_2, 0:3]
        self.right_finger_angvel_2 = self.body_angvel[:, self.right_finger_body_id_env_2, 0:3]
        self.right_finger_jacobian_2 = self.jacobian[:, self.right_finger_body_id_env_2 - 2, 0:6, 9:16]  # minus 1 because base is fixed

        self.left_finger_force = self.contact_force[:, self.left_finger_body_id_env, 0:3]
        self.left_finger_force_2 = self.contact_force[:, self.left_finger_body_id_env_2, 0:3]
        self.right_finger_force = self.contact_force[:, self.right_finger_body_id_env, 0:3]
        self.right_finger_force_2 = self.contact_force[:, self.right_finger_body_id_env_2, 0:3]
        
        """
        Above we defined:
        self.dof_pos: torch.Size([128, 18])

        self.arm_dof_pos = self.dof_pos[:, 0:7] # NOTE: index 0-7 are the arm positions for franka_1, the others are gripper positions
        self.arm_dof_pos_2 = self.dof_pos[:,9:16]  # NOTE: index 7-14 are the arm positions for franka_2, the others are gripper positions
        """

        self.gripper_dof_pos = self.dof_pos[:, 7:9]
        self.gripper_dof_pos_2 = self.dof_pos[:, 16:18]

        # Franka_1
        self.fingertip_centered_pos = self.body_pos[:, self.fingertip_centered_body_id_env, 0:3]
        self.fingertip_centered_quat = self.body_quat[:, self.fingertip_centered_body_id_env, 0:4]
        self.fingertip_centered_linvel = self.body_linvel[:, self.fingertip_centered_body_id_env, 0:3]
        self.fingertip_centered_angvel = self.body_angvel[:, self.fingertip_centered_body_id_env, 0:3]
        self.fingertip_centered_jacobian = self.jacobian[:, self.fingertip_centered_body_id_env - 1, 0:6, 0:7]  # minus 1 because base is fixed

        # NOTE: Franka_2
        self.fingertip_centered_pos_2 = self.body_pos[:, self.fingertip_centered_body_id_env_2, 0:3]
        self.fingertip_centered_quat_2 = self.body_quat[:, self.fingertip_centered_body_id_env_2, 0:4]
        self.fingertip_centered_linvel_2 = self.body_linvel[:, self.fingertip_centered_body_id_env_2, 0:3]
        self.fingertip_centered_angvel_2 = self.body_angvel[:, self.fingertip_centered_body_id_env_2, 0:3]
        self.fingertip_centered_jacobian_2 = self.jacobian[:, self.fingertip_centered_body_id_env_2 - 2, 0:6, 9:16]  # minus 1 because base is fixed       


        # Franka_1
        self.fingertip_midpoint_pos = self.fingertip_centered_pos.detach().clone()  # initial value
        self.fingertip_midpoint_quat = self.fingertip_centered_quat  # always equal
        self.fingertip_midpoint_linvel = self.fingertip_centered_linvel.detach().clone()  # initial value
        # From sum of angular velocities (https://physics.stackexchange.com/questions/547698/understanding-addition-of-angular-velocity),
        # angular velocity of midpoint w.r.t. world is equal to sum of
        # angular velocity of midpoint w.r.t. hand and angular velocity of hand w.r.t. world. 
        # Midpoint is in sliding contact (i.e., linear relative motion) with hand; angular velocity of midpoint w.r.t. hand is zero.
        # Thus, angular velocity of midpoint w.r.t. world is equal to angular velocity of hand w.r.t. world.
        self.fingertip_midpoint_angvel = self.fingertip_centered_angvel  # always equal
        self.fingertip_midpoint_jacobian = (self.left_finger_jacobian + self.right_finger_jacobian) * 0.5  # approximation

        # NOTE: Franka_2
        self.fingertip_midpoint_pos_2 = self.fingertip_centered_pos_2.detach().clone()  # initial value
        self.fingertip_midpoint_quat_2 = self.fingertip_centered_quat_2  # always equal
        self.fingertip_midpoint_linvel_2 = self.fingertip_centered_linvel_2.detach().clone()  # initial value
        # From sum of angular velocities (https://physics.stackexchange.com/questions/547698/understanding-addition-of-angular-velocity),
        # angular velocity of midpoint w.r.t. world is equal to sum of
        # angular velocity of midpoint w.r.t. hand and angular velocity of hand w.r.t. world. 
        # Midpoint is in sliding contact (i.e., linear relative motion) with hand; angular velocity of midpoint w.r.t. hand is zero.
        # Thus, angular velocity of midpoint w.r.t. world is equal to angular velocity of hand w.r.t. world.
        self.fingertip_midpoint_angvel_2 = self.fingertip_centered_angvel_2  # always equal
        self.fingertip_midpoint_jacobian_2 = (self.left_finger_jacobian_2 + self.right_finger_jacobian_2) * 0.5  # approximation


        # TODO: Do here, How do I intialize these zero arrays here?
        self.dof_torque = torch.zeros((self.num_envs, self.num_dofs), device=self.device)
        self.fingertip_contact_wrench = torch.zeros((self.num_envs, 6), device=self.device)

        self.ctrl_target_fingertip_midpoint_pos = torch.zeros((self.num_envs, 3), device=self.device)
        self.ctrl_target_fingertip_midpoint_quat = torch.zeros((self.num_envs, 4), device=self.device)
        self.ctrl_target_dof_pos = torch.zeros((self.num_envs, self.num_dofs), device=self.device)
        self.ctrl_target_gripper_dof_pos = torch.zeros((self.num_envs, 2), device=self.device)
        self.ctrl_target_fingertip_contact_wrench = torch.zeros((self.num_envs, 6), device=self.device)

        # print(self.dof_torque.shape)
        # print(self.fingertip_contact_wrench.shape)
        # print(self.ctrl_target_fingertip_midpoint_pos.shape)
        # print(self.ctrl_target_fingertip_midpoint_quat.shape)
        # print(self.ctrl_target_dof_pos.shape)
        # print(self.ctrl_target_gripper_dof_pos.shape)
        # print(self.ctrl_target_fingertip_contact_wrench.shape)
        # exit()
        """
        self.dof_torque: torch.Size([128, 18])
        self.fingertip_contact_wrench: torch.Size([128, 6])
        self.ctrl_target_fingertip_midpoint_pos: torch.Size([128, 3])
        self.ctrl_target_fingertip_midpoint_quat: torch.Size([128, 4])
        self.ctrl_target_dof_pos: torch.Size([128, 18])
        self.ctrl_target_gripper_dof_pos: torch.Size([128, 2])
        self.ctrl_target_fingertip_contact_wrench: torch.Size([128, 6])
        """

        # Intialize value for Franka_2

        self.fingertip_contact_wrench_2 = torch.zeros((self.num_envs, 6), device=self.device)

        self.ctrl_target_fingertip_midpoint_pos_2 = torch.zeros((self.num_envs, 3), device=self.device)
        self.ctrl_target_fingertip_midpoint_quat_2 = torch.zeros((self.num_envs, 4), device=self.device)

        self.ctrl_target_gripper_dof_pos_2 = torch.zeros((self.num_envs, 2), device=self.device)
        self.ctrl_target_fingertip_contact_wrench_2 = torch.zeros((self.num_envs, 6), device=self.device)

        # Previous actions
        """
        self.num_actions = 12
        """
        self.prev_actions = torch.zeros((self.num_envs, self.num_actions*2), device=self.device)
        print("self.prev_actions: ", self.prev_actions.shape) # (128, 24)


    def refresh_base_tensors(self):
        """Refresh tensors."""
        # NOTE: Tensor refresh functions should be called once per step, before setters.

        self.gym.refresh_dof_state_tensor(self.sim)
        self.gym.refresh_actor_root_state_tensor(self.sim)
        self.gym.refresh_rigid_body_state_tensor(self.sim)
        self.gym.refresh_dof_force_tensor(self.sim)
        self.gym.refresh_net_contact_force_tensor(self.sim)
        self.gym.refresh_jacobian_tensors(self.sim)
        self.gym.refresh_mass_matrix_tensors(self.sim)

        # Franka_1
        self.finger_midpoint_pos = (self.left_finger_pos + self.right_finger_pos) * 0.5
        self.fingertip_midpoint_pos = fc.translate_along_local_z(pos=self.finger_midpoint_pos,
                                                                 quat=self.hand_quat,
                                                                 offset=self.asset_info_franka_table.franka_finger_length,
                                                                 device=self.device)
        # TODO: Add relative velocity term (see https://dynamicsmotioncontrol487379916.files.wordpress.com/2020/11/21-me258pointmovingrigidbody.pdf)
        self.fingertip_midpoint_linvel = self.fingertip_centered_linvel + torch.cross(self.fingertip_centered_angvel,
                                                                                      (self.fingertip_midpoint_pos - self.fingertip_centered_pos),
                                                                                      dim=1)
        self.fingertip_midpoint_jacobian = (self.left_finger_jacobian + self.right_finger_jacobian) * 0.5  # approximation

        # Franka_2
        self.finger_midpoint_pos_2 = (self.left_finger_pos_2 + self.right_finger_pos_2) * 0.5
        self.fingertip_midpoint_pos_2 = fc.translate_along_local_z(pos=self.finger_midpoint_pos_2,
                                                                 quat=self.hand_quat_2,
                                                                 offset=self.asset_info_franka_table.franka_finger_length,
                                                                 device=self.device)
        # TODO: Add relative velocity term (see https://dynamicsmotioncontrol487379916.files.wordpress.com/2020/11/21-me258pointmovingrigidbody.pdf)
        self.fingertip_midpoint_linvel_2 = self.fingertip_centered_linvel_2 + torch.cross(self.fingertip_centered_angvel_2,
                                                                                      (self.fingertip_midpoint_pos_2 - self.fingertip_centered_pos_2),
                                                                                      dim=1)
        self.fingertip_midpoint_jacobian_2 = (self.left_finger_jacobian_2 + self.right_finger_jacobian_2) * 0.5  # approximation


    def parse_controller_spec(self):
        """Parse controller specification into lower-level controller configuration."""

        cfg_ctrl_keys = {'num_envs',
                         'jacobian_type',
                         'gripper_prop_gains',
                         'gripper_deriv_gains',
                         'motor_ctrl_mode',
                         'gain_space',
                         'ik_method',
                         'joint_prop_gains',
                         'joint_deriv_gains',
                         'do_motion_ctrl',
                         'task_prop_gains',
                         'task_deriv_gains',
                         'do_inertial_comp',
                         'motion_ctrl_axes',
                         'do_force_ctrl',
                         'force_ctrl_method',
                         'wrench_prop_gains',
                         'force_ctrl_axes'}
        self.cfg_ctrl = {cfg_ctrl_key: None for cfg_ctrl_key in cfg_ctrl_keys}

        # TODO: Look Through THIS!!!!!!!!!!!!!!!!!!!!!!!!!!!!

        self.cfg_ctrl['num_envs'] = self.num_envs
        self.cfg_ctrl['jacobian_type'] = self.cfg_task.ctrl.all.jacobian_type
        self.cfg_ctrl['gripper_prop_gains'] = torch.tensor(self.cfg_task.ctrl.all.gripper_prop_gains,
                                                           device=self.device).repeat((self.num_envs, 1))
        self.cfg_ctrl['gripper_deriv_gains'] = torch.tensor(self.cfg_task.ctrl.all.gripper_deriv_gains,
                                                            device=self.device).repeat((self.num_envs, 1))

        ctrl_type = self.cfg_task.ctrl.ctrl_type
        print("ctrl_type: ", ctrl_type)
        # ctrl_type == joint_space_id




        if ctrl_type == 'gym_default':
            self.cfg_ctrl['motor_ctrl_mode'] = 'gym'
            self.cfg_ctrl['gain_space'] = 'joint'
            self.cfg_ctrl['ik_method'] = self.cfg_task.ctrl.gym_default.ik_method
            self.cfg_ctrl['joint_prop_gains'] = torch.tensor(self.cfg_task.ctrl.gym_default.joint_prop_gains,
                                                             device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['joint_deriv_gains'] = torch.tensor(self.cfg_task.ctrl.gym_default.joint_deriv_gains,
                                                              device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['gripper_prop_gains'] = torch.tensor(self.cfg_task.ctrl.gym_default.gripper_prop_gains,
                                                               device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['gripper_deriv_gains'] = torch.tensor(self.cfg_task.ctrl.gym_default.gripper_deriv_gains,
                                                                device=self.device).repeat((self.num_envs, 1))
        elif ctrl_type == 'joint_space_ik':
            self.cfg_ctrl['motor_ctrl_mode'] = 'manual'
            self.cfg_ctrl['gain_space'] = 'joint'
            self.cfg_ctrl['ik_method'] = self.cfg_task.ctrl.joint_space_ik.ik_method
            self.cfg_ctrl['joint_prop_gains'] = torch.tensor(self.cfg_task.ctrl.joint_space_ik.joint_prop_gains,
                                                             device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['joint_deriv_gains'] = torch.tensor(self.cfg_task.ctrl.joint_space_ik.joint_deriv_gains,
                                                              device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['do_inertial_comp'] = False



        elif ctrl_type == 'joint_space_id':
            # This is reached
            self.cfg_ctrl['motor_ctrl_mode'] = 'manual'
            self.cfg_ctrl['gain_space'] = 'joint'
            self.cfg_ctrl['ik_method'] = self.cfg_task.ctrl.joint_space_id.ik_method
            self.cfg_ctrl['joint_prop_gains'] = torch.tensor(self.cfg_task.ctrl.joint_space_id.joint_prop_gains,
                                                             device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['joint_deriv_gains'] = torch.tensor(self.cfg_task.ctrl.joint_space_id.joint_deriv_gains,
                                                              device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['do_inertial_comp'] = True
        
        
        
        elif ctrl_type == 'task_space_impedance':
            self.cfg_ctrl['motor_ctrl_mode'] = 'manual'
            self.cfg_ctrl['gain_space'] = 'task'
            self.cfg_ctrl['do_motion_ctrl'] = True
            self.cfg_ctrl['task_prop_gains'] = torch.tensor(self.cfg_task.ctrl.task_space_impedance.task_prop_gains,
                                                            device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['task_deriv_gains'] = torch.tensor(self.cfg_task.ctrl.task_space_impedance.task_deriv_gains,
                                                             device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['do_inertial_comp'] = False
            self.cfg_ctrl['motion_ctrl_axes'] = torch.tensor(self.cfg_task.ctrl.task_space_impedance.motion_ctrl_axes,
                                                             device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['do_force_ctrl'] = False
        elif ctrl_type == 'operational_space_motion':
            self.cfg_ctrl['motor_ctrl_mode'] = 'manual'
            self.cfg_ctrl['gain_space'] = 'task'
            self.cfg_ctrl['do_motion_ctrl'] = True
            self.cfg_ctrl['task_prop_gains'] = torch.tensor(self.cfg_task.ctrl.operational_space_motion.task_prop_gains,
                                                            device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['task_deriv_gains'] = torch.tensor(
                self.cfg_task.ctrl.operational_space_motion.task_deriv_gains, device=self.device).repeat(
                (self.num_envs, 1))
            self.cfg_ctrl['do_inertial_comp'] = True
            self.cfg_ctrl['motion_ctrl_axes'] = torch.tensor(
                self.cfg_task.ctrl.operational_space_motion.motion_ctrl_axes, device=self.device).repeat(
                (self.num_envs, 1))
            self.cfg_ctrl['do_force_ctrl'] = False
        elif ctrl_type == 'open_loop_force':
            self.cfg_ctrl['motor_ctrl_mode'] = 'manual'
            self.cfg_ctrl['gain_space'] = 'task'
            self.cfg_ctrl['do_motion_ctrl'] = False
            self.cfg_ctrl['do_force_ctrl'] = True
            self.cfg_ctrl['force_ctrl_method'] = 'open'
            self.cfg_ctrl['force_ctrl_axes'] = torch.tensor(self.cfg_task.ctrl.open_loop_force.force_ctrl_axes,
                                                            device=self.device).repeat((self.num_envs, 1))
        elif ctrl_type == 'closed_loop_force':
            self.cfg_ctrl['motor_ctrl_mode'] = 'manual'
            self.cfg_ctrl['gain_space'] = 'task'
            self.cfg_ctrl['do_motion_ctrl'] = False
            self.cfg_ctrl['do_force_ctrl'] = True
            self.cfg_ctrl['force_ctrl_method'] = 'closed'
            self.cfg_ctrl['wrench_prop_gains'] = torch.tensor(self.cfg_task.ctrl.closed_loop_force.wrench_prop_gains,
                                                              device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['force_ctrl_axes'] = torch.tensor(self.cfg_task.ctrl.closed_loop_force.force_ctrl_axes,
                                                            device=self.device).repeat((self.num_envs, 1))
        elif ctrl_type == 'hybrid_force_motion':
            self.cfg_ctrl['motor_ctrl_mode'] = 'manual'
            self.cfg_ctrl['gain_space'] = 'task'
            self.cfg_ctrl['do_motion_ctrl'] = True
            self.cfg_ctrl['task_prop_gains'] = torch.tensor(self.cfg_task.ctrl.hybrid_force_motion.task_prop_gains,
                                                            device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['task_deriv_gains'] = torch.tensor(self.cfg_task.ctrl.hybrid_force_motion.task_deriv_gains,
                                                             device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['do_inertial_comp'] = True
            self.cfg_ctrl['motion_ctrl_axes'] = torch.tensor(self.cfg_task.ctrl.hybrid_force_motion.motion_ctrl_axes,
                                                             device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['do_force_ctrl'] = True
            self.cfg_ctrl['force_ctrl_method'] = 'closed'
            self.cfg_ctrl['wrench_prop_gains'] = torch.tensor(self.cfg_task.ctrl.hybrid_force_motion.wrench_prop_gains,
                                                              device=self.device).repeat((self.num_envs, 1))
            self.cfg_ctrl['force_ctrl_axes'] = torch.tensor(self.cfg_task.ctrl.hybrid_force_motion.force_ctrl_axes,
                                                            device=self.device).repeat((self.num_envs, 1))

        if self.cfg_ctrl['motor_ctrl_mode'] == 'gym':
            prop_gains = torch.cat((self.cfg_ctrl['joint_prop_gains'],
                                    self.cfg_ctrl['gripper_prop_gains']), dim=-1).to('cpu')
            deriv_gains = torch.cat((self.cfg_ctrl['joint_deriv_gains'],
                                     self.cfg_ctrl['gripper_deriv_gains']), dim=-1).to('cpu')
            # No tensor API for getting/setting actor DOF props; thus, loop required
            for env_ptr, franka_handle, prop_gain, deriv_gain in zip(self.env_ptrs, self.franka_handles, prop_gains,
                                                                     deriv_gains):
                franka_dof_props = self.gym.get_actor_dof_properties(env_ptr, franka_handle)
                franka_dof_props['driveMode'][:] = gymapi.DOF_MODE_POS
                franka_dof_props['stiffness'] = prop_gain
                franka_dof_props['damping'] = deriv_gain
                self.gym.set_actor_dof_properties(env_ptr, franka_handle, franka_dof_props)
        elif self.cfg_ctrl['motor_ctrl_mode'] == 'manual':
            # This is reached
            # No tensor API for getting/setting actor DOF props; thus, loop required
            print("env_ptr: ", self.env_ptrs)
            print("franka_handles: ", self.franka_handles)
            # extra loop variable for franka_2
            for env_ptr, franka_handle, franka_handle_2 in zip(self.env_ptrs, self.franka_handles, self.franka_handles_2):
                # Franka_1
                franka_dof_props = self.gym.get_actor_dof_properties(env_ptr, franka_handle)
                franka_dof_props['driveMode'][:] = gymapi.DOF_MODE_EFFORT
                franka_dof_props['stiffness'][:] = 0.0  # zero passive stiffness
                franka_dof_props['damping'][:] = 0.0  # zero passive damping

                # Franka_2
                franka_dof_props_2 = self.gym.get_actor_dof_properties(env_ptr, franka_handle_2)
                franka_dof_props_2['driveMode'][:] = gymapi.DOF_MODE_EFFORT
                franka_dof_props_2['stiffness'][:] = 0.0  # zero passive stiffness
                franka_dof_props_2['damping'][:] = 0.0  # zero passive damping

                # franka_2
                self.gym.set_actor_dof_properties(env_ptr, franka_handle, franka_dof_props)
                # franka_2
                self.gym.set_actor_dof_properties(env_ptr, franka_handle_2, franka_dof_props_2)


        # print("self.cfg_ctrl: ", self.cfg_ctrl)

    def generate_ctrl_signals(self):
        """Get Jacobian. Set Franka DOF position targets or DOF torques."""

        """
        default jacobian_type = geometric
        """

        # Get desired Jacobian
        if self.cfg_ctrl['jacobian_type'] == 'geometric':
            
            self.fingertip_midpoint_jacobian_tf = self.fingertip_midpoint_jacobian
            self.fingertip_midpoint_jacobian_tf_2 = self.fingertip_midpoint_jacobian_2


        elif self.cfg_ctrl['jacobian_type'] == 'analytic':
            self.fingertip_midpoint_jacobian_tf = fc.get_analytic_jacobian(
                fingertip_quat=self.fingertip_quat,
                fingertip_jacobian=self.fingertip_midpoint_jacobian,
                num_envs=self.num_envs,
                device=self.device)

        # Set PD joint pos target or joint torque

        """
        self.cfg_ctrl['motor_ctrl_mode'] = manual
        """

        if self.cfg_ctrl['motor_ctrl_mode'] == 'gym':
            self._set_dof_pos_target()
        elif self.cfg_ctrl['motor_ctrl_mode'] == 'manual':
            # NOTE: This is reached
            self._set_dof_torque()
            self._set_dof_torque_2()
            # print("self.dof_torque: ", self.dof_torque.shape)
            # print("self.dof_torque_2: ", self.dof_torque_2.shape)
            # concat self.dof_torque
            self.dof_torque = torch.cat((self.dof_torque, self.dof_torque_2), dim=1)
            # print("concatenated dof_torque: ", self.dof_torque.shape)
            self._wrap_tensor()

    def _set_dof_pos_target(self):
        """Set Franka DOF position target to move fingertips towards target pose."""

        self.ctrl_target_dof_pos = fc.compute_dof_pos_target(
            cfg_ctrl=self.cfg_ctrl,
            arm_dof_pos=self.arm_dof_pos,
            fingertip_midpoint_pos=self.fingertip_midpoint_pos,
            fingertip_midpoint_quat=self.fingertip_midpoint_quat,
            jacobian=self.fingertip_midpoint_jacobian_tf,
            ctrl_target_fingertip_midpoint_pos=self.ctrl_target_fingertip_midpoint_pos,
            ctrl_target_fingertip_midpoint_quat=self.ctrl_target_fingertip_midpoint_quat,
            ctrl_target_gripper_dof_pos=self.ctrl_target_gripper_dof_pos,
            device=self.device)

        self.gym.set_dof_position_target_tensor_indexed(self.sim,
                                                        gymtorch.unwrap_tensor(self.ctrl_target_dof_pos),
                                                        gymtorch.unwrap_tensor(self.franka_actor_ids_sim),
                                                        len(self.franka_actor_ids_sim))

    # This is used to wrap tensor
    def _wrap_tensor(self):
        # print("franka_actor_ids_sim: ", self.franka_actor_ids_sim)
        # print("franka_actor_ids_sim_2: ", self.franka_actor_ids_sim_2)

        """
        franka_actor_ids_sim:  tensor([  0,   5,  10,  15,  20,  25,  30,  35,  40,  45,  50,  55,  60,  65,
         70,  75,  80,  85,  90,  95, 100, 105, 110, 115, 120, 125, 130, 135,
        140, 145, 150, 155, 160, 165, 170, 175, 180, 185, 190, 195, 200, 205,
        210, 215, 220, 225, 230, 235, 240, 245, 250, 255, 260, 265, 270, 275,
        280, 285, 290, 295, 300, 305, 310, 315, 320, 325, 330, 335, 340, 345,
        350, 355, 360, 365, 370, 375, 380, 385, 390, 395, 400, 405, 410, 415,
        420, 425, 430, 435, 440, 445, 450, 455, 460, 465, 470, 475, 480, 485,
        490, 495, 500, 505, 510, 515, 520, 525, 530, 535, 540, 545, 550, 555,
        560, 565, 570, 575, 580, 585, 590, 595, 600, 605, 610, 615, 620, 625,
        630, 635], device='cuda:0', dtype=torch.int32)
        franka_actor_ids_sim_2:  tensor([  0,   5,  10,  15,  20,  25,  30,  35,  40,  45,  50,  55,  60,  65,
         70,  75,  80,  85,  90,  95, 100, 105, 110, 115, 120, 125, 130, 135,
        140, 145, 150, 155, 160, 165, 170, 175, 180, 185, 190, 195, 200, 205,
        210, 215, 220, 225, 230, 235, 240, 245, 250, 255, 260, 265, 270, 275,
        280, 285, 290, 295, 300, 305, 310, 315, 320, 325, 330, 335, 340, 345,
        350, 355, 360, 365, 370, 375, 380, 385, 390, 395, 400, 405, 410, 415,
        420, 425, 430, 435, 440, 445, 450, 455, 460, 465, 470, 475, 480, 485,
        490, 495, 500, 505, 510, 515, 520, 525, 530, 535, 540, 545, 550, 555,
        560, 565, 570, 575, 580, 585, 590, 595, 600, 605, 610, 615, 620, 625,
        630, 635], device='cuda:0', dtype=torch.int32)
        """

        self.franka_actor_ids_sim_concat = torch.cat((self.franka_actor_ids_sim, self.franka_actor_ids_sim_2), dim=0)
        # print("length of franka_actor_ids_sim_concatenate: ", len(self.franka_actor_ids_sim_concat))
        """
        size of franka_actor_ids_sim_concatenate: 256
        """

        self.gym.set_dof_actuation_force_tensor_indexed(self.sim,
                                                        gymtorch.unwrap_tensor(self.dof_torque),
                                                        gymtorch.unwrap_tensor(self.franka_actor_ids_sim_concat),
                                                        len(self.franka_actor_ids_sim_concat))                  

    def _set_dof_torque(self):
        """Set Franka DOF torque to move fingertips towards target pose."""

        self.dof_torque = fc.compute_dof_torque(
            cfg_ctrl=self.cfg_ctrl,
            dof_pos=self.dof_pos,
            dof_vel=self.dof_vel,
            fingertip_midpoint_pos=self.fingertip_midpoint_pos,
            fingertip_midpoint_quat=self.fingertip_midpoint_quat,
            fingertip_midpoint_linvel=self.fingertip_midpoint_linvel,
            fingertip_midpoint_angvel=self.fingertip_midpoint_angvel,
            left_finger_force=self.left_finger_force,
            right_finger_force=self.right_finger_force,
            jacobian=self.fingertip_midpoint_jacobian_tf,
            arm_mass_matrix=self.arm_mass_matrix,
            ctrl_target_gripper_dof_pos=self.ctrl_target_gripper_dof_pos,
            ctrl_target_fingertip_midpoint_pos=self.ctrl_target_fingertip_midpoint_pos,
            ctrl_target_fingertip_midpoint_quat=self.ctrl_target_fingertip_midpoint_quat,
            ctrl_target_fingertip_contact_wrench=self.ctrl_target_fingertip_contact_wrench,
            device=self.device)

        # self.gym.set_dof_actuation_force_tensor_indexed(self.sim,
        #                                                 gymtorch.unwrap_tensor(self.dof_torque),
        #                                                 gymtorch.unwrap_tensor(self.franka_actor_ids_sim),
        #                                                 len(self.franka_actor_ids_sim))

    def _set_dof_torque_2(self):
        """Set Franka DOF torque to move fingertips towards target pose."""

        self.dof_torque_2 = fc.compute_dof_torque_2(
            cfg_ctrl=self.cfg_ctrl,
            dof_pos=self.dof_pos,
            dof_vel=self.dof_vel,
            fingertip_midpoint_pos=self.fingertip_midpoint_pos_2,
            fingertip_midpoint_quat=self.fingertip_midpoint_quat_2,
            fingertip_midpoint_linvel=self.fingertip_midpoint_linvel_2,
            fingertip_midpoint_angvel=self.fingertip_midpoint_angvel_2,
            left_finger_force=self.left_finger_force_2,
            right_finger_force=self.right_finger_force_2,
            jacobian=self.fingertip_midpoint_jacobian_tf_2,
            arm_mass_matrix=self.arm_mass_matrix_2,
            ctrl_target_gripper_dof_pos=self.ctrl_target_gripper_dof_pos_2,
            ctrl_target_fingertip_midpoint_pos=self.ctrl_target_fingertip_midpoint_pos_2,
            ctrl_target_fingertip_midpoint_quat=self.ctrl_target_fingertip_midpoint_quat_2,
            ctrl_target_fingertip_contact_wrench=self.ctrl_target_fingertip_contact_wrench_2,
            device=self.device)

        # self.gym.set_dof_actuation_force_tensor_indexed(self.sim,
        #                                                 gymtorch.unwrap_tensor(self.dof_torque),
        #                                                 gymtorch.unwrap_tensor(self.franka_actor_ids_sim),
        #                                                 len(self.franka_actor_ids_sim))

    def print_sdf_warning(self):
        """Generate SDF warning message."""

        logger.warn('Please be patient: SDFs may be generating, which may take a few minutes. Terminating prematurely may result in a corrupted SDF cache.')

    def enable_gravity(self, gravity_mag):
        """Enable gravity."""

        sim_params = self.gym.get_sim_params(self.sim)
        sim_params.gravity.z = -gravity_mag
        self.gym.set_sim_params(self.sim, sim_params)

    def disable_gravity(self):
        """Disable gravity."""

        sim_params = self.gym.get_sim_params(self.sim)
        sim_params.gravity.z = 0.0
        self.gym.set_sim_params(self.sim, sim_params)

    def export_scene(self, label):
        """Export scene to USD."""

        usd_export_options = gymapi.UsdExportOptions()
        usd_export_options.export_physics = False

        usd_exporter = self.gym.create_usd_exporter(usd_export_options)
        self.gym.export_usd_sim(usd_exporter, self.sim, label)
        sys.exit()

    def extract_poses(self):
        """Extract poses of all bodies."""

        if not hasattr(self, 'export_pos'):
            self.export_pos = []
            self.export_rot = []
            self.frame_count = 0

        pos = self.body_pos
        rot = self.body_quat

        self.export_pos.append(pos.cpu().numpy().copy())
        self.export_rot.append(rot.cpu().numpy().copy())
        self.frame_count += 1

        if len(self.export_pos) == self.max_episode_length:
            output_dir = self.__class__.__name__
            save_dir = os.path.join('usd', output_dir)
            os.makedirs(output_dir, exist_ok=True)

            print(f'Exporting poses to {output_dir}...')
            np.save(os.path.join(save_dir, 'body_position.npy'), np.array(self.export_pos))
            np.save(os.path.join(save_dir, 'body_rotation.npy'), np.array(self.export_rot))
            print('Export completed.')
            sys.exit()
