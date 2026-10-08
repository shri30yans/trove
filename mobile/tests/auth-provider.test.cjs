const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { createLoader } = require('./helpers/typescript-loader.cjs');

test('email sign-in keeps a deletion-pending account on the locked state', async () => {
  const statuses = [];
  let stateIndex = 0;
  const react = {
    createContext: () => ({ Provider: 'AuthProvider' }),
    useCallback: (callback) => callback,
    useContext: () => null,
    useEffect: () => {},
    useMemo: (factory) => factory(),
    useState: (initial) => {
      const index = stateIndex++;
      let value = initial;
      return [value, (next) => {
        value = typeof next === 'function' ? next(value) : next;
        if (index === 0) statuses.push(value);
      }];
    },
  };
  const api = {
    cancelAccountDeletionFromTrove: async () => {},
    clearStoredAuthSession: async () => {},
    deleteAccountFromTrove: async () => {},
    getAccountDeletionStatus: async () => ({
      deletionScheduled: true,
      deleteAfter: '2026-10-15T00:00:00.000Z',
      deletionComplete: false,
      deletionCancellable: true,
    }),
    hasSavedSession: async () => false,
    setSessionExpiredHandler: () => {},
    signInWithPassword: async () => {},
    signOutFromTrove: async () => {},
  };
  const load = createLoader({
    react,
    'react/jsx-runtime': { jsx: (type, props) => ({ type, props }) },
    '../api/client': api,
    '../features/sync/delete-local-captures': { deleteLocalCaptures: async () => {} },
    '../storage/local-preferences': { clearAccountLocalPreferences: async () => {} },
  });
  const { AuthProvider } = load('src/providers/auth-provider.tsx');
  const element = AuthProvider({ children: null });

  await element.props.value.signIn('reader@example.test', 'synthetic-password');

  assert.deepEqual(statuses, ['deletion_pending']);
});

test('the root hides all feature navigation while deletion is pending', () => {
  const source = fs.readFileSync(require('node:path').join(__dirname, '../src/app/_layout.tsx'), 'utf8');
  assert.match(source, /if \(status === 'deletion_pending'\) return <AccountDeletionScreen/);
  assert.match(source, /return <TroveProvider><RootStack \/><\/TroveProvider>/);
  assert.ok(source.indexOf("status === 'deletion_pending'") < source.indexOf('return <TroveProvider>'));
});
