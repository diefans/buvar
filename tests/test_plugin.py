def test_bootstrap(event_loop):
    from buvar import plugin, components

    cmps = components.Components()

    results = plugin.bootstrap(
        'tests.foo_plugin',
        components=cmps,
        loop=event_loop
    )

    assert results == [{'foo': 'foo'}, 'bar', 'baz']
