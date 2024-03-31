#
#
#

from os.path import dirname, join

from natsort import natsort_keygen
from yaml import SafeDumper, SafeLoader, dump, load
from yaml.constructor import ConstructorError
from yaml.representer import SafeRepresenter

from .context import ContextDict

_natsort_key = natsort_keygen()


class ContextLoader(SafeLoader):
    def _pairs(self, node):
        self.flatten_mapping(node)
        pairs = self.construct_pairs(node)
        start_mark = node.start_mark
        context = f'{start_mark.name}, line {start_mark.line+1}, column {start_mark.column+1}'
        return ContextDict(pairs, context=context), pairs, context

    def _construct(self, node):
        return self._pairs(node)[0]

    def include(self, node):
        mark = self.get_mark()
        directory = dirname(mark.name)

        filename = join(directory, self.construct_scalar(node))

        with open(filename, 'r') as fh:
            return safe_load(fh, self.__class__)


ContextLoader.add_constructor('!include', ContextLoader.include)
ContextLoader.add_constructor(
    ContextLoader.DEFAULT_MAPPING_TAG, ContextLoader._construct
)


# Found http://stackoverflow.com/a/21912744 which guided me on how to hook in
# here
class SortEnforcingLoader(ContextLoader):
    def get_sorting_key(self, d):
        return _natsort_key(d)

    def _construct(self, node):
        ret, pairs, context = self._pairs(node)

        keys = [d[0] for d in pairs]
        keys_sorted = sorted(keys, key=self.get_sorting_key)
        for key in keys:
            expected = keys_sorted.pop(0)
            if key != expected:
                raise ConstructorError(
                    None,
                    None,
                    'keys out of order: '
                    f'expected {expected} got {key} at {context}',
                )

        return ret


class DnsSortEnforcingLoader(SortEnforcingLoader):
    '''
    Enforces DNS hierarchy aware sorting order
    '''

    def get_sorting_key(self, d):
        return _natsort_key(reversed(d.split('.')))


for cls in (SortEnforcingLoader, DnsSortEnforcingLoader):
    cls.add_constructor(cls.DEFAULT_MAPPING_TAG, cls._construct)


def safe_load(stream, enforce_order=True):
    loader = ContextLoader
    if enforce_order == 'dns':
        loader = DnsSortEnforcingLoader
    elif enforce_order:
        loader = SortEnforcingLoader
    return load(stream, loader)


class SortingDumper(SafeDumper):
    '''
    This sorts keys alphanumerically in a "natural" manner where things with
    the number 2 come before the number 12.

    See https://www.xormedia.com/natural-sort-order-with-zero-padding/ for
    more info
    '''

    def get_sorting_key(self, d):
        return _natsort_key(d)

    def _representer(self, data):
        data = sorted(data.items(), key=lambda d: self.get_sorting_key(d[0]))
        return self.represent_mapping(self.DEFAULT_MAPPING_TAG, data)


class DnsSortingDumper(SortingDumper):
    '''
    Same as SortingDumper, but sorts keys in DNS hierarchy aware manner.

    For example: a.test.com, sub2.a.test.com, sub10.a.test.com, b.test.com
    '''

    def get_sorting_key(self, d):
        return _natsort_key(reversed(d.split('.')))


for cls in (SortingDumper, DnsSortingDumper):
    cls.add_representer(dict, cls._representer)
    # This should handle all the record value types which are ultimately either str
    # or dict at some point in their inheritance hierarchy
    cls.add_multi_representer(str, SafeRepresenter.represent_str)
    cls.add_multi_representer(dict, cls._representer)


def safe_dump(data, fh, enforce_order=True, **options):
    kwargs = {
        'canonical': False,
        'indent': 2,
        'default_style': '',
        'default_flow_style': False,
        'explicit_start': True,
    }
    kwargs.update(options)
    dump(
        data,
        fh,
        SortingDumper if enforce_order != 'dns' else DnsSortingDumper,
        **kwargs,
    )
