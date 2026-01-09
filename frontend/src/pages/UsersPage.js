import React, { useState, useEffect } from 'react';
import Layout from '../components/Layout';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Badge } from '../components/ui/badge';
import { Input } from '../components/ui/input';
import { Label } from '../components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '../components/ui/dialog';
import { Switch } from '../components/ui/switch';
import { usersAPI } from '../lib/api';
import { getRoleLabel, formatDate } from '../lib/utils';
import { toast } from 'sonner';
import { Plus, Pencil, Trash2, Users, Shield } from 'lucide-react';

const roles = [
  { value: 'admin', label: 'Administrador', icon: '👑' },
  { value: 'waiter', label: 'Garçom', icon: '🍽️' },
  { value: 'cashier', label: 'Caixa', icon: '💰' },
  { value: 'kitchen', label: 'Cozinha', icon: '👨‍🍳' },
  { value: 'bar', label: 'Bar', icon: '🍸' },
];

export default function UsersPage() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [form, setForm] = useState({
    name: '',
    email: '',
    password: '',
    role: 'waiter',
    is_active: true,
  });

  useEffect(() => {
    fetchUsers();
  }, []);

  const fetchUsers = async () => {
    try {
      const response = await usersAPI.getAll();
      setUsers(response.data);
    } catch (error) {
      toast.error('Erro ao carregar usuários');
    } finally {
      setLoading(false);
    }
  };

  const openDialog = (user = null) => {
    if (user) {
      setEditingUser(user);
      setForm({
        name: user.name,
        email: user.email,
        password: '',
        role: user.role,
        is_active: user.is_active,
      });
    } else {
      setEditingUser(null);
      setForm({
        name: '',
        email: '',
        password: '',
        role: 'waiter',
        is_active: true,
      });
    }
    setIsDialogOpen(true);
  };

  const handleSave = async () => {
    if (!form.name || !form.email || (!editingUser && !form.password)) {
      toast.error('Preencha todos os campos obrigatórios');
      return;
    }

    try {
      if (editingUser) {
        const updateData = { ...form };
        if (!updateData.password) delete updateData.password;
        await usersAPI.update(editingUser.id, updateData);
        toast.success('Usuário atualizado!');
      } else {
        await usersAPI.create(form);
        toast.success('Usuário criado!');
      }
      setIsDialogOpen(false);
      fetchUsers();
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Erro ao salvar usuário');
    }
  };

  const handleDelete = async (id) => {
    if (!window.confirm('Deseja excluir este usuário?')) return;

    try {
      await usersAPI.delete(id);
      toast.success('Usuário excluído');
      fetchUsers();
    } catch (error) {
      toast.error('Erro ao excluir usuário');
    }
  };

  const getRoleBadgeColor = (role) => {
    const colors = {
      admin: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-300',
      waiter: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300',
      cashier: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300',
      kitchen: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-300',
      bar: 'bg-pink-100 text-pink-800 dark:bg-pink-900/30 dark:text-pink-300',
    };
    return colors[role] || 'bg-gray-100 text-gray-800';
  };

  if (loading) {
    return (
      <Layout title="Usuários">
        <div className="flex items-center justify-center h-64">
          <div className="animate-pulse text-primary font-heading text-xl">
            Carregando...
          </div>
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Usuários">
      <div className="space-y-6" data-testid="users-page">
        {/* Header */}
        <div className="flex justify-between items-center">
          <p className="text-muted-foreground">
            {users.length} usuário(s) cadastrado(s)
          </p>
          <Button onClick={() => openDialog()} data-testid="add-user-btn">
            <Plus className="h-4 w-4 mr-2" />
            Novo Usuário
          </Button>
        </div>

        {/* Users Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {users.map(user => (
            <Card key={user.id} className="card-hover" data-testid={`user-card-${user.id}`}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="h-12 w-12 rounded-full bg-primary/20 flex items-center justify-center">
                      <span className="font-heading text-xl text-primary">
                        {user.name.charAt(0)}
                      </span>
                    </div>
                    <div>
                      <h3 className="font-medium">{user.name}</h3>
                      <p className="text-sm text-muted-foreground">{user.email}</p>
                    </div>
                  </div>
                  <Badge className={getRoleBadgeColor(user.role)}>
                    {getRoleLabel(user.role)}
                  </Badge>
                </div>

                <div className="flex items-center justify-between text-sm mb-4">
                  <span className="text-muted-foreground">Status:</span>
                  <Badge variant={user.is_active ? 'default' : 'secondary'}>
                    {user.is_active ? 'Ativo' : 'Inativo'}
                  </Badge>
                </div>

                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    className="flex-1"
                    onClick={() => openDialog(user)}
                    data-testid={`edit-user-${user.id}`}
                  >
                    <Pencil className="h-4 w-4 mr-2" />
                    Editar
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="text-destructive"
                    onClick={() => handleDelete(user.id)}
                    data-testid={`delete-user-${user.id}`}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>

        {users.length === 0 && (
          <div className="text-center py-12">
            <Users className="h-12 w-12 mx-auto text-muted-foreground mb-4" />
            <p className="text-muted-foreground">Nenhum usuário cadastrado</p>
          </div>
        )}

        {/* Dialog */}
        <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle className="font-heading">
                {editingUser ? 'Editar Usuário' : 'Novo Usuário'}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4">
              <div className="space-y-2">
                <Label>Nome *</Label>
                <Input
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  data-testid="user-name-input"
                />
              </div>
              <div className="space-y-2">
                <Label>E-mail *</Label>
                <Input
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  data-testid="user-email-input"
                />
              </div>
              <div className="space-y-2">
                <Label>{editingUser ? 'Nova Senha (deixe em branco para manter)' : 'Senha *'}</Label>
                <Input
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  data-testid="user-password-input"
                />
              </div>
              <div className="space-y-2">
                <Label>Perfil</Label>
                <Select
                  value={form.role}
                  onValueChange={(v) => setForm({ ...form, role: v })}
                >
                  <SelectTrigger data-testid="user-role-select">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {roles.map(role => (
                      <SelectItem key={role.value} value={role.value}>
                        {role.icon} {role.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex items-center gap-2">
                <Switch
                  checked={form.is_active}
                  onCheckedChange={(v) => setForm({ ...form, is_active: v })}
                />
                <Label>Usuário ativo</Label>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => setIsDialogOpen(false)}>
                Cancelar
              </Button>
              <Button onClick={handleSave} data-testid="save-user-btn">
                Salvar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>
    </Layout>
  );
}
