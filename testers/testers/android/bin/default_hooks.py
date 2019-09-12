import os
import shutil

def before_each_android(settings, **kwargs):
    """ remove target dir """
    shutil.rmtree('target', ignore_errors=True)

HOOKS = [before_each_android]
