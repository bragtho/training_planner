import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'api.dart';

enum AuthStatus { unknown, signedOut, signedIn }

class AuthController extends Notifier<AuthStatus> {
  late final ApiClient api;

  @override
  AuthStatus build() {
    api = ApiClient(ref.read(tokenStoreProvider), onUnauthorized: signOut);
    _restore();
    return AuthStatus.unknown;
  }

  Future<void> _restore() async {
    final t = await ref.read(tokenStoreProvider).read();
    state = t == null ? AuthStatus.signedOut : AuthStatus.signedIn;
  }

  Future<void> _auth(String path, String email, String password) async {
    final r = await api.dio
        .post(path, data: {'email': email, 'password': password});
    await ref.read(tokenStoreProvider).write(r.data['access_token'] as String);
    state = AuthStatus.signedIn;
  }

  Future<void> login(String email, String password) =>
      _auth('/auth/login', email, password);
  Future<void> register(String email, String password) =>
      _auth('/auth/register', email, password);

  Future<void> signOut() async {
    await ref.read(tokenStoreProvider).write(null);
    state = AuthStatus.signedOut;
  }
}

final authProvider =
    NotifierProvider<AuthController, AuthStatus>(AuthController.new);

final apiProvider = Provider((ref) {
  ref.watch(authProvider);
  return ref.read(authProvider.notifier).api;
});
