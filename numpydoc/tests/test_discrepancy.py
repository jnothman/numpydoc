
from nose.tools import assert_list_equal
from nose.tools import assert_raises
from nose.tools import assert_equal

from numpydoc.discrepancy import get_diff

from numpydoc.tests.discrepancy_tests import some_function, SomeClass

EXP1 = '''
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -12,8 +12,8 @@
         Woobar
 
-    qqq
-
+    bbb
     ccc
         Hello world
+    ddd
 
     Returns
'''.lstrip()

EXP2 = '''
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -12,8 +12,8 @@
         Woobar
 
-    qqq
-
     ccc
         Hello world
+    bbb
+    ddd
 
     Returns
'''.lstrip()


def test_get_diff():
    out = get_diff(some_function, ['aaa', 'bbb', 'ccc', 'ddd'],
                   path='path/to/file.py')
    assert_list_equal(EXP1.split('\n'), out.split('\n'))

    out = get_diff(some_function, ['aaa', 'bbb', 'ccc'], {'ddd'},
                   path='path/to/file.py')
    assert_list_equal(EXP1.split('\n'), out.split('\n'))

    out = get_diff(some_function, ['aaa', 'bbb'], {'ccc', 'ddd'},
                   path='path/to/file.py')
    assert_list_equal(EXP1.split('\n'), out.split('\n'))

    out = get_diff(some_function, ['aaa'], {'bbb', 'ccc', 'ddd'},
                   path='path/to/file.py')
    assert_list_equal(EXP2.split('\n'), out.split('\n'))

    out = get_diff(some_function, [], {'aaa', 'bbb', 'ccc', 'ddd'},
                   path='path/to/file.py')
    assert_list_equal(EXP2.split('\n'), out.split('\n'))

    out = get_diff(some_function, [], {'aaa', 'bbb', 'ccc', 'ddd'},
                   path='path/to/myfile.py')
    assert_list_equal(EXP2.replace('/file', '/myfile').split('\n'),
                      out.split('\n'))


def test_get_diff_empty():
    # NIL transformation
    out = get_diff(some_function, [], {'aaa', 'qqq', 'ccc'},
                   path='path/to/file.py')
    assert_equal(out, '')


def test_get_diff_validation():
    assert_raises(ValueError, get_diff, some_function, ['aaa'], {'aaa'})


EXP3 = '''
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -23,4 +23,5 @@
         long
         description
+    nothing
     """
     pass
'''.lstrip()


def test_get_diff_section():
    out = get_diff(some_function, ['something', 'nothing'], set(),
                   section='Returns', path='path/to/file.py')
    assert_list_equal(EXP3.split('\n'), out.split('\n'))


EXP4 = '''
--- a/path/to/file.py
+++ b/path/to/file.py
@@ -36,4 +36,5 @@
     ccc
         Hello world
+    ddd
     """
     pass
'''.lstrip()


def test_get_diff_class():
    out = get_diff(SomeClass, ['ccc', 'ddd'], set(),
                   path='path/to/file.py')
    assert_list_equal(EXP4.split('\n'), out.split('\n'))
