from cmath import phase
from math import gamma
import gpt as g
import numpy as np
from utils.io_corr import *

#ordered list of gamma matrix identifiers, needed for the tag in the correlator output
my_gammas = ["5", "T", "T5", "X", "X5", "Y", "Y5", "Z", "Z5", "I", "SXT", "SXY", "SXZ", "SYT", "SYZ", "SZT"]

ordered_list_of_gammas = [g.gamma[5], g.gamma["T"], g.gamma["T"]*g.gamma[5],
                                      g.gamma["X"], g.gamma["X"]*g.gamma[5], 
                                      g.gamma["Y"], g.gamma["Y"]*g.gamma[5],
                                      g.gamma["Z"], g.gamma["Z"]*g.gamma[5], 
                                      g.gamma["I"], g.gamma["SigmaXT"], 
                                      g.gamma["SigmaXY"], g.gamma["SigmaXZ"], 
                                      g.gamma["SigmaZT"]
                            ]

class pion_measurement:
    def __init__(self, parameters):
        self.plist = parameters["plist"]
        self.width = parameters["width"]
        self.pos_boost = parameters["pos_boost"]
        self.neg_boost = parameters["neg_boost"]
        self.save_propagators = parameters["save_propagators"]

    def set_input_facilities(self, corr_file):
        self.input_correlator = g.corr_io.reader(corr_file)

    def set_output_facilities(self, corr_file, prop_file):
        self.output_correlator = g.corr_io.writer(corr_file)
        
        if(self.save_propagators):
            self.output = g.gpt_io.writer(prop_file)

    def propagator_input(self, prop_file):
        g.message(f"Reading propagator file {prop_file}")
        read_props = g.load(prop_file)
        return read_props

    def propagator_output_k0(self, tag, prop_f):

        g.message("Saving forward propagator")
        prop_f_tag = "%s/%s" % (tag, str(self.pos_boost))
        self.output.write({prop_f_tag: prop_f})
        self.output.flush()
        g.message("Propagator IO done")

    def propagator_output(self, tag, prop_f, prop_b):

        g.message("Saving forward propagator")
        prop_f_tag = "%s/%s" % (tag, str(self.pos_boost)) 
        self.output.write({prop_f_tag: prop_f})
        self.output.flush()
        g.message("Saving backward propagator")
        prop_b_tag = "%s/%s" % (tag, str(self.neg_boost))
        self.output.write({prop_b_tag: prop_b})
        self.output.flush()
        g.message("Propagator IO done")

    def make_64I_inverter(self, U, evec_file):
        l_exact = g.qcd.fermion.mobius(
            U,
            {
                #64I params
                "mass": 0.000678,
                "M5": 1.8,
                "b": 1.5,
                "c": 0.5,
                "Ls": 12,
                "boundary_phases": [1.0, 1.0, 1.0, 1.0],
                },

        )

        l_sloppy = l_exact.converted(g.single)
        g.message(f"Loading eigenvectors from {evec_file}")
        g.mem_report(details=False)
        eig = g.load(evec_file, grids=l_sloppy.F_grid_eo)

        g.mem_report(details=False)
        pin = g.pin(eig[1], g.accelerator)
        g.message("creating deflated solvers")

        light_innerL_inverter = g.algorithms.inverter.preconditioned(
           g.qcd.fermion.preconditioner.eo1_ne(parity=g.odd),
           g.algorithms.inverter.sequence(
               g.algorithms.inverter.coarse_deflate(
                   eig[1],
                   eig[0],
                   eig[2],
                   block=400,
                   fine_block=4,
                   linear_combination_block=32,
               ),
               g.algorithms.inverter.split(
                   g.algorithms.inverter.cg({"eps": 1e-8, "maxiter": 200}),
                   mpi_split=g.default.get_ivec("--mpi_split", None, 4),
               ),
           ),
        )

        light_innerH_inverter = g.algorithms.inverter.preconditioned(
            g.qcd.fermion.preconditioner.eo1_ne(parity=g.odd),
            g.algorithms.inverter.sequence(
               g.algorithms.inverter.coarse_deflate(
                   eig[1],
                   eig[0],
                   eig[2],
                   block=400,
                   fine_block=4,
                   linear_combination_block=32,
               ),
               g.algorithms.inverter.split(
                   g.algorithms.inverter.cg({"eps": 1e-4, "maxiter": 200}),
                   mpi_split=g.default.get_ivec("--mpi_split", None, 4),
               ),
           ),
        )

        g.mem_report(details=False)
        light_exact_inverter = g.algorithms.inverter.defect_correcting(g.algorithms.inverter.mixed_precision(light_innerL_inverter, g.single, g.double),
            eps=1e-8,
            maxiter=12,
        )

        light_sloppy_inverter = g.algorithms.inverter.defect_correcting(g.algorithms.inverter.mixed_precision(light_innerH_inverter, g.single, g.double),
            eps=1e-4,
            maxiter=12,
        )


        ############### final inverter definitions
        prop_l_sloppy = l_exact.propagator(light_sloppy_inverter).grouped(4)
        prop_l_exact = l_exact.propagator(light_exact_inverter).grouped(4)

        return prop_l_exact, prop_l_sloppy, pin

    def make_debugging_inverter(self, U):

        l_exact = g.qcd.fermion.mobius(
            U,
            {
                #64I params
                "mass": 0.0006203,
                "M5": 1.8,
                "b": 1.5,
                "c": 0.5,
                "Ls": 12,
                "boundary_phases": [1.0, 1.0, 1.0, 1.0],},
                #48I params
                #"mass": 0.00078,
                #"M5": 1.8,
                #"b": 1.5,
                #"c": 0.5,
                #"Ls": 24,
                #"boundary_phases": [1.0, 1.0, 1.0, -1.0],},
        )

        l_sloppy = l_exact.converted(g.single)

        light_innerL_inverter = g.algorithms.inverter.preconditioned(g.qcd.fermion.preconditioner.eo2_ne(), g.algorithms.inverter.cg(eps = 1e-2, maxiter = 10000))
        light_innerH_inverter = g.algorithms.inverter.preconditioned(g.qcd.fermion.preconditioner.eo2_ne(), g.algorithms.inverter.cg(eps = 1e-8, maxiter = 200))

        prop_l_sloppy = l_exact.propagator(light_innerH_inverter).grouped(6)
        prop_l_exact = l_exact.propagator(light_innerL_inverter).grouped(6)
        return prop_l_exact, prop_l_sloppy


    ############## make list of complex phases for momentum proj.
    def make_mom_phases(self, grid, origin=None):    
        one = g.identity(g.complex(grid))
        pp = [-2 * np.pi * np.array(p) / grid.fdimensions for p in self.plist]
       
        P = g.exp_ixp(pp, origin)
       
        mom = [g.eval(pp*one) for pp in P]
        return mom

    # create Wilson lines from all --> all + dz for all dz in 0,zmax
    def create_WL(self, U):
        W = []
        W.append(g.qcd.gauge.unit(U[2].grid)[0])
        for dz in range(0, self.zmax):
            W.append(g.eval(W[dz] * g.cshift(U[2], 2, dz)))
                
        return W

    #function that does the contractions for the smeared-smeared pion 2pt function
    def contract_2pt(self, prop_f, prop_b, phases, trafo, tag):

        tmp_trafo = g.convert(trafo, prop_f.grid.precision)

        prop_f = g.create.smear.boosted_smearing(tmp_trafo, prop_f, w=self.width, boost=self.pos_boost)
        prop_b = g.create.smear.boosted_smearing(tmp_trafo, prop_b, w=self.width, boost=self.neg_boost)
     
        #corr = g.slice_trDA(prop_f,g.gamma[5]*g.adj(g.gamma[5]*prop_b*g.gamma[5]),phases, 3) 
        corr = g.slice_trDA(g.gamma[5]*g.adj(g.gamma[5]*prop_b*g.gamma[5]), prop_f, phases, 3) 
        #corr = g.slice_trDA(prop_f,g.adj(prop_b),phases, 3)
        if g.rank() == 0:
            save_c2pt_hdf5(corr, tag, my_gammas, self.plist)
        del corr 

    #function that creates boosted, smeared src.
    def create_src_2pt(self, pos, trafo, grid):
        
        srcD = g.mspincolor(grid)
        
        
        g.create.point(srcD, pos)
        g.message("point src set")

        srcDm = g.create.smear.boosted_smearing(trafo, srcD, w=self.width, boost=self.neg_boost)
        g.message("pos. boosted src done")
        
        srcDp = g.create.smear.boosted_smearing(trafo, srcD, w=self.width, boost=self.pos_boost)
        g.message("neg. boosted src done")
        
        return srcDp, srcDm


'''---------------------------------------------'''
'''-------------------pion DA-------------------'''
'''---------------------------------------------'''

class pion_DA_measurement(pion_measurement):
    def __init__(self,parameters):
        self.zmax = parameters["zmax"]
        self.pzmin = parameters["pzmin"]
        self.pzmax = parameters["pzmax"]
        self.plist = [ [0,0, pz, 0] for pz in range(self.pzmin,self.pzmax)]
        self.width = parameters["width"]
        self.pos_boost = parameters["pos_boost"]
        self.neg_boost = parameters["neg_boost"]
        self.save_propagators = parameters["save_propagators"]

    # create Wilson lines from all --> all +- dz for all dz in 0,zmax
    def create_DA_WL(self, U):

        index_list = []

        # z in [0, zmax-1]
        W = []
        W.append(g.qcd.gauge.unit(U[2].grid)[0]) # z = 0
        for dz in range(0, self.zmax-1):
            W.append(g.eval(W[dz] * g.cshift(U[2], 2, dz))) # z from 1 to zmax-1
        index_list = [[0,i,0,0] for i in range(0, self.zmax)]
        # z in [-1, -(zmax-1)]
        V = []
        V.append(g.qcd.gauge.unit(U[2].grid)[0])
        for dz in range(-1, -self.zmax, -1):
            V.append(g.eval(V[dz] * g.adj(g.cshift(U[2], 2, dz))))
        index_list += [[0,i,0,0] for i in range(-1, -self.zmax, -1)]
                
        return W+V[1:], index_list

    # Creating list of W*prop_b for all z
    def constr_DA_bprop(self, prop_b, W, W_index_list):

        prop_list = []
        # W_index_list[i] = bz
        for i, idx in enumerate(W_index_list):
            current_bz = idx[1]
            prop_list.append(g.eval(g.gamma[5]*g.adj(g.gamma[5]*g.eval(W[i] * g.cshift(prop_b,2,current_bz))*g.gamma[5])))
        return prop_list

    def contract_DA(self, prop_f, prop_b, phases, tag, W_index_list, i_sub):

        corr = g.slice_trDA(prop_b,prop_f,phases, 3)
        if g.rank() == 0:
            #self.save_qTMDWF_hdf5(corr, tag, my_gammas)
            save_qTMDWF_hdf5_subset(corr, tag, my_gammas, self.plist, W_index_list, i_sub)
        del corr




'''---------------------------------------------'''
'''-----------------pion TMDWF------------------'''
'''---------------------------------------------'''

class TMD_WF_measurement(pion_measurement):
    def __init__(self,parameters):
        self.eta = parameters["eta"]
        self.b_z = parameters["b_z"]
        self.b_T = parameters["b_T"]
        self.pzmin = parameters["pzmin"]
        self.pzmax = parameters["pzmax"]
        self.plist = [ [0,0, pz, 0] for pz in range(self.pzmin,self.pzmax)]
        self.width = parameters["width"]
        self.pos_boost = parameters["pos_boost"]
        self.neg_boost = parameters["neg_boost"]
        self.save_propagators = parameters["save_propagators"]

    # if i_sub=0, will create a new .h5 file, elif i_sub != 0, will add data into exist .h5 file
    def contract_TMD(self, prop_f, prop_b, phases, tag, W_index_list, i_sub):

        corr = g.slice_trDA(prop_b,prop_f,phases, 3)
        if g.rank() == 0:
            #self.save_qTMDWF_hdf5(corr, tag, my_gammas)
            save_qTMDWF_hdf5_subset(corr, tag, my_gammas, self.plist, W_index_list, i_sub)
        del corr

    def create_src_TMD(self, pos, trafo, grid):
        
        srcD = g.mspincolor(grid)
        srcD[:] = 0
        
        g.create.point(srcD, pos)
        
        srcDm = g.create.smear.boosted_smearing(trafo, srcD, w=self.width, boost=self.neg_boost)
        srcDp = g.create.smear.boosted_smearing(trafo, srcD, w=self.width, boost=self.pos_boost)
        
        del srcD
        return srcDp, srcDm

    def constr_TMD_bprop(self, prop_b, W, W_index_list):
        # prop_list = [prop_b,]
        # FIXME: temporarily remove the no Wilson line contraction
        prop_list = []
        # W_index_list[i] = [bT, bz, eta, Tdir]
        for i, idx in enumerate(W_index_list):
            current_b_T = idx[0]
            current_bz = idx[1]
            current_eta = idx[2]
            transverse_direction = idx[3]
            #g.mem_report(details=False)
            prop_list.append(g.eval(g.gamma[5]*g.adj(g.gamma[5]*g.eval(W[i] * g.cshift(g.cshift(prop_b,transverse_direction,current_b_T),2,2*current_bz))*g.gamma[5])))
            #g.mem_report(details=False)
        return prop_list

    def create_TMD_WL(self, U):

        W = []
        index_list = []

        # create Wilson lines from all to all + (eta+bz) + b_perp - (eta-b_z)
        for transverse_direction in [0,1]:
            for current_eta in self.eta:
                for current_bz in range(0, self.b_z):
                    for current_b_T in range (0, self.b_T):

                        prv_link = g.qcd.gauge.unit(U[2].grid)[0]
                        current_link = prv_link
                        # FIXME: phase need to be corrected due to source position
                        for dz in range(0, current_eta+current_bz):
                            current_link=g.eval(prv_link * g.cshift(U[2],2, dz))
                            prv_link=current_link

                        for dx in range(0, current_b_T):
                            current_link=g.eval(prv_link * g.cshift(g.cshift(U[transverse_direction], 2, current_eta+current_bz),transverse_direction, dx))
                            prv_link=current_link


                        for dz in range(0, current_eta-current_bz):
                            current_link=g.eval(prv_link * g.adj(g.cshift(g.cshift(g.cshift(U[2], 2, current_eta+current_bz-1), transverse_direction, current_b_T),2,-dz)))
                            prv_link=current_link

                        W.append(current_link)
                        index_list.append([current_b_T, current_bz, current_eta, transverse_direction])
        return W, index_list

    def create_TMD_WL_sequential(self, U):

        W = []
        index_list = []

        # create Wilson lines from (all - bz) to (all + eta + b_perp + b_z)
        for transverse_direction in [0,1]:
            for current_eta in self.eta:
                for current_b_T in range (0, self.b_T):
                    for current_bz in range(0, self.b_z):
                        
                        if current_bz == 0:
                            prv_link = g.qcd.gauge.unit(U[2].grid)[0]
                            for dz in range(0, current_eta+current_bz):
                                current_link=g.eval(prv_link * g.cshift(U[2],2, dz))
                                prv_link=current_link
                            for dx in range(0, current_b_T):
                                current_link=g.eval(prv_link * g.cshift(g.cshift(U[transverse_direction], 2, current_eta+current_bz),transverse_direction, dx))
                                prv_link=current_link
                            for dz in range(0, current_eta-current_bz):
                                current_link=g.eval(prv_link * g.adj(g.cshift(g.cshift(g.cshift(U[2], 2, current_eta+current_bz-1), transverse_direction, current_b_T),2,-dz)))
                                prv_link=current_link
                        else:
                            forward_link = g.cshift(g.cshift(U[2], transverse_direction, current_b_T), 2, current_bz-1)
                            bckward_link = g.cshift(U[2], 2, -current_bz)
                            current_link = g.eval(bckward_link * prv_link * forward_link)
                            prv_link = current_link

                        W.append(current_link)
                        index_list.append([current_b_T, current_bz, current_eta, transverse_direction])
        return W, index_list


    def create_TMD_WL_sequential_Dir(self, U):

        W = []
        index_list = []


        # create Wilson lines from (all - bz) to (all + eta + b_perp + b_z)
        for transverse_direction in [0,1]:
            for current_eta in self.eta:

                # ------------------------------------------------#
                # --------------- possitive eta ------------------#
                # ------------------------------------------------#
                if current_eta > 0:
                    for current_b_T in range (-self.b_T, self.b_T):

                        # bz = 0
                        prv_link = g.qcd.gauge.unit(U[2].grid)[0]
                        for dz in range(0, current_eta):
                            current_link=g.eval(prv_link * g.cshift(U[2],2, dz))
                            prv_link=current_link
                        if current_b_T >= 0:
                            for dx in range(0, current_b_T):
                                current_link=g.eval(prv_link * g.cshift(g.cshift(U[transverse_direction], 2, current_eta),transverse_direction, dx))
                                prv_link=current_link
                        else:
                            for dx in range(-1, current_b_T-1, -1):
                                current_link=g.eval(prv_link * g.adj(g.cshift(g.cshift(U[transverse_direction], 2, current_eta),transverse_direction, dx)))
                                prv_link=current_link
                        for dz in range(0, current_eta):
                            current_link=g.eval(prv_link * g.adj(g.cshift(g.cshift(g.cshift(U[2], 2, current_eta-1), transverse_direction, current_b_T),2,-dz)))
                            prv_link=current_link
                        W.append(current_link)
                        index_list.append([current_b_T, 0, current_eta, transverse_direction])

                        # bz > 0
                        for current_bz in range(1, self.b_z):
                            forward_link = g.cshift(g.cshift(U[2], transverse_direction, current_b_T), 2, current_bz-1)
                            bckward_link = g.cshift(U[2], 2, -current_bz)
                            current_link = g.eval(bckward_link * prv_link * forward_link)
                            prv_link = current_link
                            W.append(current_link)
                            index_list.append([current_b_T, current_bz, current_eta, transverse_direction])

                        # bz < 0
                        for current_bz in range(-1, -self.b_z, -1):
                            forward_link = g.adj(g.cshift(g.cshift(U[2], transverse_direction, current_b_T), 2, current_bz))
                            bckward_link = g.adj(g.cshift(U[2], 2, -current_bz-1))
                            current_link = g.eval(bckward_link * prv_link * forward_link)
                            prv_link = current_link
                            W.append(current_link)
                            index_list.append([current_b_T, current_bz, current_eta, transverse_direction])

                # ------------------------------------------------#
                # ---------------- negative eta ------------------#
                # ------------------------------------------------#
                elif current_eta < 0:
                    for current_b_T in range (-self.b_T, self.b_T):

                        # bz = 0
                        prv_link = g.qcd.gauge.unit(U[2].grid)[0]
                        for dz in range(0, current_eta-1, -1):
                            current_link=g.eval(prv_link * g.adj(g.cshift(U[2],2, dz)))
                            prv_link=current_link
                        if current_b_T >= 0:
                            for dx in range(0, current_b_T):
                                current_link=g.eval(prv_link * g.cshift(g.cshift(U[transverse_direction], 2, current_eta),transverse_direction, dx))
                                prv_link=current_link
                        else:
                            for dx in range(-1, current_b_T-1, -1):
                                current_link=g.eval(prv_link * g.adj(g.cshift(g.cshift(U[transverse_direction], 2, current_eta),transverse_direction, dx)))
                                prv_link=current_link
                        for dz in range(0, current_eta, -1):
                            current_link=g.eval(prv_link * g.adj(g.cshift(g.cshift(g.cshift(U[2], 2, current_eta), transverse_direction, current_b_T),2,-dz)))
                            prv_link=current_link
                        W.append(current_link)
                        index_list.append([current_b_T, 0, current_eta, transverse_direction])

                        # bz > 0
                        for current_bz in range(1, self.b_z):
                            forward_link = g.cshift(g.cshift(U[2], transverse_direction, current_b_T), 2, current_bz-1)
                            bckward_link = g.cshift(U[2], 2, -current_bz)
                            current_link = g.eval(bckward_link * prv_link * forward_link)
                            prv_link = current_link
                            W.append(current_link)
                            index_list.append([current_b_T, current_bz, current_eta, transverse_direction])

                        # bz < 0
                        for current_bz in range(-1, -self.b_z, -1):
                            forward_link = g.adj(g.cshift(g.cshift(U[2], transverse_direction, current_b_T), 2, current_bz))
                            bckward_link = g.adj(g.cshift(U[2], 2, -current_bz-1))
                            current_link = g.eval(bckward_link * prv_link * forward_link)
                            prv_link = current_link
                            W.append(current_link)
                            index_list.append([current_b_T, current_bz, current_eta, transverse_direction])

        return W, index_list
