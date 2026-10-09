import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api.dart';
import '../../core/auth.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';

class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  final _server = TextEditingController();
  bool _register = false;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    ref.read(tokenStoreProvider).readUrl().then((u) {
      if (mounted) setState(() => _server.text = u ?? apiBaseUrl);
    });
  }

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    _server.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    final auth = ref.read(authProvider.notifier);
    try {
      var server = _server.text.trim();
      if (server.isNotEmpty && !server.startsWith('http')) {
        server = 'http://$server';
      }
      await ref
          .read(tokenStoreProvider)
          .writeUrl(server.replaceFirst(RegExp(r'/+$'), ''));
      final email = _email.text.trim();
      await (_register
          ? auth.register(email, _password.text)
          : auth.login(email, _password.text));
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 900;
    final form = Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(Gap.xl),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 400),
          child: _buildForm(context, showLogo: !wide),
        ),
      ),
    );
    return Scaffold(
      body: wide
          ? Row(children: [
              const Expanded(child: _HeroPanel()),
              Expanded(child: form),
            ])
          : SafeArea(child: form),
    );
  }

  Widget _buildForm(BuildContext context, {required bool showLogo}) {
    final t = Theme.of(context);
    return Form(
      key: _form,
      child: AutofillGroup(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (showLogo) ...[
              const Align(alignment: Alignment.centerLeft, child: AppLogo(showName: true, size: 48)),
              const SizedBox(height: Gap.xxl),
            ],
            Text(_register ? 'Konto erstellen' : 'Willkommen zurück', style: t.textTheme.headlineMedium),
            const SizedBox(height: Gap.xs),
            Text(
              _register
                  ? 'Starte mit Deinem persönlichen KI-Coach.'
                  : 'Melde Dich an, um Dein Training zu planen.',
              style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: Gap.xl),
            TextFormField(
              controller: _email,
              keyboardType: TextInputType.emailAddress,
              autofillHints: const [AutofillHints.email],
              decoration: const InputDecoration(labelText: 'E-Mail', prefixIcon: Icon(Icons.mail_outline_rounded)),
              validator: (v) => (v == null || !v.contains('@')) ? 'Gültige E-Mail eingeben' : null,
            ),
            const SizedBox(height: Gap.md),
            TextFormField(
              controller: _password,
              obscureText: true,
              autofillHints: const [AutofillHints.password],
              decoration: const InputDecoration(labelText: 'Passwort', prefixIcon: Icon(Icons.lock_outline_rounded)),
              onFieldSubmitted: (_) => _submit(),
              validator: (v) => (v == null || v.length < 8) ? 'Mindestens 8 Zeichen' : null,
            ),
            const SizedBox(height: Gap.md),
            Theme(
              data: t.copyWith(dividerColor: Colors.transparent),
              child: ExpansionTile(
                tilePadding: EdgeInsets.zero,
                childrenPadding: const EdgeInsets.only(bottom: Gap.sm),
                leading: Icon(Icons.dns_outlined, size: 20, color: t.colorScheme.onSurfaceVariant),
                title: Text('Server', style: t.textTheme.bodyMedium),
                subtitle: Text(_server.text, style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
                children: [
                  TextFormField(
                    controller: _server,
                    keyboardType: TextInputType.url,
                    onChanged: (_) => setState(() {}),
                    decoration: const InputDecoration(
                      labelText: 'Server-Adresse',
                      helperText: 'z. B. http://100.x.y.z:8000 (Tailscale) oder http://192.168.0.45:8000',
                    ),
                  ),
                ],
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: Gap.sm),
              Container(
                padding: const EdgeInsets.all(Gap.md),
                decoration: BoxDecoration(
                  color: t.colorScheme.errorContainer,
                  borderRadius: BorderRadius.circular(Radii.md),
                ),
                child: Row(children: [
                  Icon(Icons.error_outline_rounded, color: t.colorScheme.onErrorContainer, size: 20),
                  const SizedBox(width: Gap.sm),
                  Expanded(child: Text(_error!, style: TextStyle(color: t.colorScheme.onErrorContainer))),
                ]),
              ),
            ],
            const SizedBox(height: Gap.lg),
            FilledButton(
              onPressed: _busy ? null : _submit,
              child: _busy
                  ? const SizedBox(height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2))
                  : Text(_register ? 'Registrieren' : 'Anmelden'),
            ),
            const SizedBox(height: Gap.sm),
            TextButton(
              onPressed: _busy ? null : () => setState(() => _register = !_register),
              child: Text(_register ? 'Schon ein Konto? Anmelden' : 'Neu hier? Konto erstellen'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Linke Seite auf breiten Bildschirmen: Verlauf mit Nutzenversprechen.
class _HeroPanel extends StatelessWidget {
  const _HeroPanel();

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    const features = [
      (Icons.insights_rounded, 'Fitness, Ermüdung und Form auf einen Blick'),
      (Icons.calendar_month_rounded, 'Trainingskalender mit Plan- und Ist-Vergleich'),
      (Icons.auto_awesome, 'KI-Coach, der Deine Woche plant'),
      (Icons.sync_alt_rounded, 'Automatischer Import aus Strava'),
    ];
    return Container(
      decoration: const BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [Color(0xFF0B1730), AppColors.brand, Color(0xFF1E3A8A)],
        ),
      ),
      padding: const EdgeInsets.all(56),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const AppLogo(size: 44),
          const SizedBox(width: Gap.md),
          Text('Wattlab', style: t.textTheme.titleLarge?.copyWith(color: Colors.white)),
        ]),
        const Spacer(),
        Text('Trainiere smarter,\nnicht nur härter.',
            style: t.textTheme.displaySmall?.copyWith(color: Colors.white, height: 1.15)),
        const SizedBox(height: Gap.lg),
        Text('Deine Radtrainings-Plattform mit persönlichem KI-Coach.',
            style: t.textTheme.titleMedium?.copyWith(color: Colors.white.withValues(alpha: 0.8), fontWeight: FontWeight.w400)),
        const SizedBox(height: Gap.xxl),
        for (final f in features)
          Padding(
            padding: const EdgeInsets.only(bottom: Gap.md),
            child: Row(children: [
              Container(
                padding: const EdgeInsets.all(Gap.sm),
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(Radii.md),
                ),
                child: Icon(f.$1, color: Colors.white, size: 20),
              ),
              const SizedBox(width: Gap.md),
              Expanded(child: Text(f.$2, style: t.textTheme.bodyLarge?.copyWith(color: Colors.white))),
            ]),
          ),
        const Spacer(),
      ]),
    );
  }
}

