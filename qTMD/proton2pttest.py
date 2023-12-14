#!/usr/bin/env python3

import gpt as g
import os
import sys
import math
import numpy as np

from qTMD.gpt_proton_qTMD_utils import proton_measurement

groups = {
    "Frontier_batch_0": {
        "confs": [
            "1410",
        ],
        "evec_fmt": "/lustre/orion/proj-shared/nph159/data/64I/%s.evecs/lanczos.output",
        "conf_fmt": "/lustre/orion/proj-shared/nph159/data/64I/ckpoint_lat.Coulomb.%s",
    },
}

parameters = {
    "plist" : [[0,0,0,0]],
    "width" :41.0,
    "pos_boost": [0,0,0],
    "save_propagators": False
}
# def uud_two_point(Q1, Q2, kernel):
#     dq = g.qcd.baryon.diquark(g(Q1 * kernel), g(kernel * Q2))
#     return g(g.color_trace(g.spin_trace(dq) * Q1 + dq * Q1))

# def proton(Q1, Q2):
#     C = 1j * g.gamma[1].tensor() * g.gamma[3].tensor()
#     Gamma = C * g.gamma[5].tensor()
#     Pp = (g.gamma["I"].tensor() + g.gamma[3].tensor()) * 0.25
#     return g(g.trace(uud_two_point(Q1,Q2,Gamma) * Pp))

jobs = {
    "test_exact_0": {
        "exact": 1,
        "sloppy": 32,
        "low": 0,
    },
}

jobs_per_run = g.default.get_int("--gpt_jobs", 1)

# find jobs for this run
def get_job(only_on_conf=None):
    # statistics
    n = 0
    for group in groups:
        for job in jobs:
            for conf in groups[group]["confs"]:
                n += 1

    jid = -1
    for group in groups:
        for conf in groups[group]["confs"]:
            for job in jobs:
                jid += 1
                if only_on_conf is not None and only_on_conf != conf:
                    continue
                return group, job, conf, jid, n

    return None

if g.rank() == 0:
    first_job = get_job()
    run_jobs = str(
        list(
            filter(
                lambda x: x is not None,
                [first_job] + [get_job(first_job[2]) for i in range(1, jobs_per_run)],
            )
        )
    ).encode("utf-8")
else:
    run_jobs = bytes()
run_jobs = eval(g.broadcast(0, run_jobs).decode("utf-8"))

conf = run_jobs[0][2]
group = run_jobs[0][0]



U = g.load(groups[group]["conf_fmt"] % conf)

L = U[0].grid.fdimensions
Measurement = proton_measurement(parameters)

U_prime, trafo = g.gauge_fix(U, maxiter=10000)

del U_prime

prop_exact, prop_sloppy, pin = Measurement.make_64I_inverter(U, groups[group]["evec_fmt"] % conf)

src_position = [0,0,0,0]

src = g.mspincolor(U[0].grid)#Measurement.create_src_2pt(src_position,trafo, U[0].grid)
g.create.point(src,src_position)

prop_exact_f = g.eval(prop_exact * src)

phases = Measurement.make_mom_phases(U[0].grid, src_position)

correlator = Measurement.contract_2pt_plain(prop_exact_f, phases)

g.message(correlator)
