import re
import difflib
import pydoc
import inspect
import importlib
import sys

from .docscrape import NumpyDocString


def get_param_diff(obj, positional=(), keyword=(), section='Parameters',
                   path=None):
    """Propose changes to the docstring to match requirements

    Parameters
    ----------
    obj : function or class with numpydoc docstring
    positional : sequence of str, optional
        Sought positional argument names in order
    keyword : set of str, optional
        Sought keyword argument names for arbitrary order
    section : str, optional
        A :class:`NumpyDocString` section key which indicates a parameter list.
    path : str, optional
        The path that the diff is to patch. Defaults to source file.

    Returns
    -------
    diff : str
        A unified diff which patches the parameter list section to match
        the sought keywords. Keyword entries are removed if absent from
        ``positional`` and ``keyword``; reordered or inserted in the correct
        place according to ``positional``; and appended in alphabetical order
        if newly found in ``keyword``.

        If there is nothing to patch, the empty string is returned.
    """
    keyword = set(keyword)
    if keyword.intersection(positional):
        raise ValueError('`positional` and `keyword` should be '
                         'non-overlapping. Found intersection %s' %
                         keyword.intersection(positional))

    lines, file_offset = inspect.getsourcelines(obj)

    # identify the offset of the docstring within `lines`
    for docstring_offset, l in enumerate(lines):
        # XXX: a brittle heuristic
        if re.match(r'\s+(\'\'\'|""")', l):
            docstring_indent = len(l) - len(l.lstrip())
            break
    else:
        raise ValueError('Failed to find docstring start for %s' % obj)
    new_name_fmt = ' ' * docstring_indent + '%s' + '\n'

    if path is None:
        path = inspect.getsourcefile(obj)

    # TODO?: some validation that our offset matches getdoc

    parsed_docstring = NumpyDocString(pydoc.getdoc(obj))

    def get_lines(idx):
        start, length = parsed_docstring._line_spans[section, idx]
        return lines[start + docstring_offset:
                     start + length + docstring_offset]

    section_start, param_list_length = parsed_docstring._line_spans[section]
    param_list_stop = section_start + param_list_length
    try:
        param_list_start, _ = parsed_docstring._line_spans[section, 0]
    except KeyError:
        # No params yet
        param_list_start = param_list_stop
    out = lines[:param_list_start + docstring_offset]
    name_to_idx = dict((name, i)
                       for i, (name, _, _)
                       in enumerate(parsed_docstring[section]))

    # match and insert positionals
    for name in positional:
        if name in name_to_idx:
            out.extend(get_lines(name_to_idx[name]))
        else:
            # Insert: line contains name only
            out.append(new_name_fmt % name)

    # matched keywords
    positional = set(positional)
    for i, (name, _, _) in enumerate(parsed_docstring[section]):
        if name in positional:
            continue
        try:
            keyword.remove(name)
        except KeyError:
            continue
        out.extend(get_lines(i))

    # Insert remaining keywords
    out.extend(new_name_fmt % name for name in sorted(keyword))

    # Be careful about following as may need to include closing of docstring

    out.extend(lines[param_list_stop + docstring_offset:])
    file_offset = ['\n'] * (file_offset - 1)
    diff = difflib.unified_diff(file_offset + lines,
                                file_offset + out,
                                fromfile='a/' + path, tofile='b/' + path,
                                n=2)  # n=2 should work for any non-empty obj
    return ''.join(diff)


def diff_parameters(obj, all_positional=False, remove=(), path=None):
    """Return a diff that updates docstring Parameters to the argspec

    Parameters
    ----------
    obj
    all_positional : boolean, optional
        If False (default), the order of documentation for arguments with
        default values  is ignored.  If True, documentation order will be
        matched to the argspec order.
    remove : collection of str
        These keyword arguments should not be documented despite appearing in
        argspec.
    path : str, optional
        The path that the diff is to patch. Defaults to source file.

    Returns
    -------
    diff : str
        A unified diff which patches the parameter list section to match
        the sought keywords.

        If there is nothing to patch, the empty string is returned.
    """
    if inspect.isclass(obj):
        # TODO: consider __new__?
        func = obj.__init__
    else:
        func = obj

    # TODO: use getfullargspec to support Py3 keyword-only args
    args, varargs_name, keywords_name, defaults = inspect.getargspec(func)

    # drop `self`
    if len(args) > 0 and args[0] == 'self':
        # TODO: consider `cls`
        args = args[1:]

    if all_positional or defaults is None:
        positional = args
        keyword = set()
    else:
        positional = args[:-len(defaults)]
        keyword = set(args[-len(defaults):])

    if varargs_name is not None:
        positional = list(positional) + [varargs_name]
    if keywords_name is not None:
        keyword.add(keywords_name)

    remove = set(remove)
    positional = [name for name in positional if name not in remove]
    keyword -= remove

    return get_param_diff(obj, positional=positional, keyword=keyword,
                          path=path)


def diff_member_parameters(module, all_positional=False, remove=(), path=None):
    """
    Parameters
    ----------
    module
    all_positional : boolean, optional
        If False (default), the order of documentation for arguments with
        default values  is ignored.  If True, documentation order will be
        matched to the argspec order.
    remove : collection of str
        These keyword arguments should not be documented despite appearing in
        argspec.
    path : str, optional
        The path that the diff is to patch. Defaults to source file per object.

    Reuturns
    --------
    unified_diff : str
    """
    diffs = []

    def append_diff(obj):
        try:
            diff = diff_parameters(obj, all_positional=all_positional,
                                   remove=remove, path=path)
        except Exception:
            # TODO: raise warning
            return

        if diff:
            diffs.append('For {0}.{1}:\n'
                         .format(inspect.getmodule(obj).__name__,
                                 obj.__name__))
            diffs.append(diff)

    for cname, cls in inspect.getmembers(module, inspect.isclass):
        if cname.startswith('_'):
            continue

        if hasattr(cls, '__init__'):
            append_diff(cls)

        for fname, func in inspect.getmembers(cls, inspect.isfunction):
            if fname == '__call__' or not fname.startswith('_'):
                append_diff(func)

    for fname, func in inspect.getmembers(module, inspect.isfunction):
        if not fname.startswith('_'):
            append_diff(func)

    return ''.join(diffs)


def main():
    """Print parameter diffs for the modules listed on the command-line
    """
    for name in sys.argv[1:]:
        module = importlib.import_module(name)
        sys.stdout.write(diff_member_parameters(module))


if __name__ == '__main__':
    main()
