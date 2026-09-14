class CreateChannelAccounts < ActiveRecord::Migration[8.1]
  def change
    create_table :channel_accounts do |t|
      t.string :platform, null: false
      t.string :account_name, null: false
      t.string :account_identifier, null: false
      t.jsonb :credentials, default: {}
      t.boolean :is_active, default: true, null: false

      t.timestamps
    end
    add_index :channel_accounts, [ :platform, :account_identifier ], unique: true
  end
end
