#  ___________________________________________________________________________
#
#  Pyomo: Python Optimization Modeling Objects
#  Copyright 2017 National Technology and Engineering Solutions of Sandia, LLC
#  Under the terms of Contract DE-NA0003525 with National Technology and 
#  Engineering Solutions of Sandia, LLC, the U.S. Government retains certain 
#  rights in this software.
#  This software is distributed under the 3-clause BSD License.
#  ___________________________________________________________________________

from pyomo.util.plugin import alias
from pyomo.core.base import Transformation, Block, Constraint
from pyomo.gdp import Disjunct

class HACK_GDP_Var_Mover(Transformation):
    alias('gdp.varmover', doc="HACK: this will move all indicator variables "
          "on the model to the top block so the writers can find them.")

    def _apply_to(self, instance, **kwds):
        assert not kwds
        count = 0
        disjunct_generator = instance.component_data_objects(
            Disjunct, descend_into=(Block, Disjunct) )
        for disjunct in disjunct_generator:
            count += 1
            var = disjunct.indicator_var
            var.doc = "%s(Moved from %s)" % (
                var.doc+" " if var.doc else "", var.name, )
            disjunct.del_component(var)
            instance.add_component("_gdp_moved_IV_%s" %(count,), var)

class  HACK_GDP_Disjunct_Reclassifier(Transformation):
    alias('gdp.reclassify', doc="HACK: this will reclassify all Disjuncts "
          "to Blocks so the current writers can find the variables")

    def _apply_to(self, instance, **kwds):
        assert not kwds
        disjunct_generator = instance.component_data_objects(
            Disjunct, descend_into=(Block, Disjunct) )
        for disjunct in disjunct_generator:
            if disjunct.active:
                logger.error("""Reclassifying an active Disjunct as a Block.
This is generally as error as it indicates that the model was not
completely relaxed before applying the gdp.reclassify transformation""")

            # Deactivate all constraints.  Note that we only need to
            # descent into blocks: we will catch disjuncts in the outer
            # loop.
            cons_in_disjunct = disjunct.component_objects(
                Constraint, descend_into=Block, active=True)
            for con in cons_in_disjunct:
                con.deactivate()

            # Reclassify this disjunct as a block
            disjunct.parent_block().reclassify_component_type(disjunct, Block)
            disjunct.activate()
